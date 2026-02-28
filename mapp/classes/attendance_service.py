from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum, Q, Case, When, DecimalField
from datetime import datetime
import datetime
import pytz
import datetime as dt
import base64
import uuid
from django.core.files.base import ContentFile
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

from mapp.models import AttendanceSession, CustomUser, HourCorrection, WorkingHoursConfig, LateArrival
from mapp.classes.payroll_service import PayrollService
from mapp.classes.logs.logs import Logs


class AttendanceService:

    @classmethod
    def get_lateness_records_paginated(
        cls,
        page: int = 1,
        page_size: int = 20,
        user_id: str = None,
        start_date=None,   # "YYYY-MM-DD" or date
        end_date=None,     # "YYYY-MM-DD" or date
        session: str = None,     # "first" | "second"
        is_excused=None,         # True | False | None
        search: str = None       # optional name/phone search
    ):
        """
        Retrieve lateness records with pagination.
        Returns stable response structure with page metadata.
        """
        try:
            # ---------
            # Sanitize pagination
            # ---------
            try:
                page = int(page) if page else 1
            except Exception:
                page = 1

            try:
                page_size = int(page_size) if page_size else 20
            except Exception:
                page_size = 20

            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 20
            if page_size > 200:
                page_size = 200  # safety cap

            qs = LateArrival.objects.select_related("user", "excused_by").all()

            # ---------
            # Filters
            # ---------
            if user_id:
                qs = qs.filter(user__user_id=user_id)

            if start_date:
                qs = qs.filter(date__gte=start_date)

            if end_date:
                qs = qs.filter(date__lte=end_date)

            if session in ["first", "second"]:
                qs = qs.filter(session=session)

            if is_excused is True:
                qs = qs.filter(is_excused=True)
            elif is_excused is False:
                qs = qs.filter(is_excused=False)

            if search:
                s = search.strip()
                if s:
                    qs = qs.filter(
                        Q(user__first_name__icontains=s) |
                        Q(user__last_name__icontains=s) |
                        Q(user__phone_number__icontains=s) |
                        Q(user__username__icontains=s)
                    )

            total_records = qs.count()

            # ---------
            # Pagination
            # ---------
            paginator = Paginator(qs, page_size)

            try:
                page_obj = paginator.page(page)
            except EmptyPage:
                # If page is out of range, return empty but valid payload
                page_obj = []

            # ---------
            # Serialize
            # ---------
            results = []
            if page_obj:
                for r in page_obj.object_list:
                    results.append({
                        "late_id": str(r.late_id),
                        "date": r.date.isoformat(),
                        "session": r.session,
                        "lateness_hours": str(r.lateness_hours),

                        "reason": r.reason,
                        "is_excused": r.is_excused,
                        "excused_at": r.excused_at.isoformat() if r.excused_at else None,

                        "expected_start_time": r.expected_start_time.isoformat() if r.expected_start_time else None,
                        "actual_clock_in_time": r.actual_clock_in_time.isoformat() if r.actual_clock_in_time else None,

                        "user": {
                            "user_id": str(r.user.user_id),
                            "full_name": r.user.full_name,
                            "phone_number": r.user.phone_number,
                            "user_role": r.user.user_role,
                        },

                        "excused_by": {
                            "user_id": str(r.excused_by.user_id),
                            "full_name": r.excused_by.full_name,
                        } if r.excused_by else None,

                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    })

            # Use correct page info even if out-of-range
            page_number = page if page_obj else page
            total_pages = paginator.num_pages if total_records > 0 else 0
            has_next = page_obj.has_next() if page_obj else False
            has_prev = page_obj.has_previous() if page_obj else False

            Logs.atuta_logger(
                f"[LATENESS_LIST] page={page_number} size={page_size} total={total_records} "
                f"filters: user_id={user_id} start_date={start_date} end_date={end_date} "
                f"session={session} is_excused={is_excused} search={search}"
            )

            return {
                "status": "success",
                "message": "lateness_records_retrieved",
                "data": {
                    "results": results,
                    "pagination": {
                        "page": page_number,
                        "page_size": page_size,
                        "total_records": total_records,
                        "total_pages": total_pages,
                        "has_next": has_next,
                        "has_previous": has_prev,
                    },
                },
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_lateness_records_paginated_failed", exc_info=e)
            return {
                "status": "error",
                "message": "get_lateness_records_paginated_failed",
            }

    @classmethod
    def check_lateness(cls, user: CustomUser, timestamp: dt.datetime):
        """
        Check lateness ONLY on clock-in, using your strict rules:

        Session detection (today only):
        - FIRST: user has no AttendanceSession record today
        - SECOND: user HAS a record today AND the latest is status='closed' and notes='break'
        - Ignore everything else (return status='ignored')

        Lateness thresholds:
        - FIRST: WorkingHoursConfig.start_time + 10 minutes
        - SECOND: CustomUser.lunch_start (HHMM int) + 10 minutes

        If late, INSERT/UPSERT LateArrival for (user, date, session).
        Fractions allowed; lateness stored in hours (Decimal 2dp).
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            if timestamp is None:
                return {"status": "error", "message": "missing_timestamp"}

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            # Work in Nairobi time
            ts_local = timestamp.astimezone(KENYA_TZ)
            today = ts_local.date()

            # Get today's latest session for this user (if any)
            latest_session = (
                AttendanceSession.objects.filter(user=user, date=today)
                .order_by("-created_at")
                .first()
            )

            # Determine FIRST vs SECOND (strict rules)
            if not latest_session:
                session_name = LateArrival.SessionChoices.FIRST
            else:
                if latest_session.status == "closed" and (latest_session.notes or "").strip().lower() == "break":
                    session_name = LateArrival.SessionChoices.SECOND
                else:
                    # Ignore everything else
                    Logs.atuta_logger(
                        f"[LATE_IGNORE] User {user.user_id} ({user.full_name}) | "
                        f"date={today} | reason=invalid_session_state | "
                        f"latest_status={latest_session.status} | latest_notes={latest_session.notes}"
                    )
                    return {"status": "ignored", "message": "invalid_session_state"}

            # Compute expected start datetime (local) + 10 min grace
            expected_dt_local = None

            if session_name == LateArrival.SessionChoices.FIRST:
                # Django weekday: Monday=0 -> Sunday=6, your mapping is 1-7
                day_of_week = ts_local.weekday() + 1

                config = WorkingHoursConfig.objects.filter(
                    user_role=user.user_role,
                    day_of_week=day_of_week,
                    is_active=True
                ).first()

                if not config:
                    Logs.atuta_logger(
                        f"[LATE_IGNORE] No working hours config for user {user.user_id} ({user.full_name}) | "
                        f"role={user.user_role} | day={day_of_week}"
                    )
                    return {"status": "ignored", "message": "no_working_hours_config"}

                expected_dt_local = dt.datetime.combine(today, config.start_time)
                if timezone.is_naive(expected_dt_local):
                    expected_dt_local = KENYA_TZ.localize(expected_dt_local)

            else:
                # SECOND session: compare against CustomUser.lunch_start (HHMM int)
                lunch_start = user.lunch_start
                if lunch_start is None:
                    Logs.atuta_logger(
                        f"[LATE_IGNORE] No lunch_start for user {user.user_id} ({user.full_name}) | date={today}"
                    )
                    return {"status": "ignored", "message": "missing_lunch_start"}

                # Convert HHMM int -> hour/minute
                hour = int(lunch_start) // 100
                minute = int(lunch_start) % 100

                # Safety (even though your clean() enforces it)
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    Logs.atuta_logger(
                        f"[LATE_IGNORE] Invalid lunch_start for user {user.user_id} ({user.full_name}) | "
                        f"lunch_start={lunch_start}"
                    )
                    return {"status": "ignored", "message": "invalid_lunch_start"}

                expected_dt_local = dt.datetime.combine(today, dt.time(hour, minute, 0))
                if timezone.is_naive(expected_dt_local):
                    expected_dt_local = KENYA_TZ.localize(expected_dt_local)

            # Add 10-minute grace
            grace_dt_local = expected_dt_local + dt.timedelta(minutes=10)

            # If on time (<= grace), do nothing
            if ts_local <= grace_dt_local:
                Logs.atuta_logger(
                    f"[LATE_OK] User {user.user_id} ({user.full_name}) | date={today} | session={session_name} | "
                    f"clock_in={ts_local} | grace={grace_dt_local}"
                )
                return {"status": "success", "message": "not_late", "session": session_name, "lateness_hours": "0.00"}

            # Late: compute lateness in hours beyond grace time
            late_seconds = (ts_local - grace_dt_local).total_seconds()
            lateness_hours = Decimal(str(late_seconds / 3600)).quantize(Decimal("0.01"))

            with transaction.atomic():
                # UPSERT behavior via update_or_create (unique constraint user/date/session)
                record, created = LateArrival.objects.update_or_create(
                    user=user,
                    date=today,
                    session=session_name,
                    defaults={
                        "lateness_hours": lateness_hours,
                        "expected_start_time": expected_dt_local.astimezone(pytz.utc),
                        "actual_clock_in_time": ts_local.astimezone(pytz.utc),
                        "reason": "Late clock-in",
                    },
                )

            Logs.atuta_logger(
                f"[LATE_RECORDED] User {user.user_id} ({user.full_name}) | date={today} | session={session_name} | "
                f"lateness_hours={lateness_hours} | expected={expected_dt_local} | grace={grace_dt_local} | actual={ts_local} | "
                f"{'created' if created else 'updated'}"
            )

            return {
                "status": "success",
                "message": "late_recorded",
                "session": session_name,
                "lateness_hours": str(lateness_hours),
                "late_id": str(record.late_id),
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"check_lateness_failed_user_{getattr(user, 'user_id', 'unknown')}",
                exc_info=e
            )
            return {"status": "error", "message": "check_lateness_failed"}

    @classmethod
    def get_hours_between_end_time_and_anchor(cls, user_id, anchor_time: dt.datetime):
        """
        Uses get_user_day_end_time(user_id) to fetch today's configured end_time,
        then calculates hours between (today at end_time) and anchor_time.

        - anchor_time: timezone-aware datetime (when system auto-clocked out user)
        Returns:
            {
            "status": "success",
            "day": <1-7>,
            "end_datetime": <aware datetime>,
            "anchor_datetime": <aware datetime>,
            "hours": <float>  # >= 0
            }
        Or:
            None / {"status":"error", "message": "..."}
        """
        try:
            if anchor_time is None:
                return {"status": "error", "message": "missing_anchor_time"}

            # Ensure anchor_time is aware
            if timezone.is_naive(anchor_time):
                anchor_time = timezone.make_aware(anchor_time)

            day_config = cls.get_user_day_end_time(user_id)
            if not day_config or not day_config.get("end_time"):
                return {"status": "error", "message": "no_working_hours_config"}

            end_time = day_config["end_time"]
            tz_name = day_config.get("timezone") or "Africa/Nairobi"
            tz = pytz.timezone(tz_name)

            # Convert anchor_time to the config timezone for correct comparison
            anchor_local = anchor_time.astimezone(tz)

            # Build end-of-day datetime on the anchor_local date
            end_dt_local = dt.datetime.combine(anchor_local.date(), end_time)
            if timezone.is_naive(end_dt_local):
                end_dt_local = tz.localize(end_dt_local)

            # Compute difference (clamp to 0 for "extra time" concept)
            diff_seconds = (anchor_local - end_dt_local).total_seconds()
            hours = round(max(diff_seconds, 0) / 3600, 2)

            return {
                "status": "success",
                "day": day_config["day"],
                "end_datetime": end_dt_local,
                "anchor_datetime": anchor_local,
                "hours": hours,
                "timezone": tz_name,
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.get_hours_between_end_time_and_anchor "
                f"for user {user_id}: {str(e)}",
                exc_info=e
            )
            return {"status": "error", "message": "calculation_failed"}

    @classmethod
    def is_within_working_hours(cls, user_id):
        """
        Returns True if current time (based on config timezone)
        is within user's configured working hours.
        Otherwise returns False.
        """
        try:
            # Fetch user
            user = CustomUser.objects.get(user_id=user_id)

            # Current server time (aware)
            now = timezone.localtime(timezone.now())

            # Django weekday: Monday=0 → Sunday=6
            day_of_week = now.weekday() + 1  # Convert to 1–7 mapping

            # Fetch working hours config
            config = WorkingHoursConfig.objects.filter(
                user_role=user.user_role,
                day_of_week=day_of_week,
                is_active=True
            ).first()

            if not config:
                Logs.atuta_logger(
                    f"No working hours config found for role={user.user_role}, day={day_of_week}"
                )
                return False

            # Convert current time to config timezone
            config_tz = pytz.timezone(config.timezone)
            now_local = timezone.now().astimezone(config_tz)

            current_time = now_local.time()

            # Normal case (no overnight shifts)
            if config.start_time <= current_time <= config.end_time:
                return True

            return False

        except CustomUser.DoesNotExist:
            Logs.atuta_logger(f"User not found in is_within_working_hours: {user_id}")
            return False

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.is_within_working_hours "
                f"for user {user_id}: {str(e)}"
            )
            return False

    @classmethod
    def auto_clock_out_overtime_users(cls):
        """
        Auto clock-out job for overtime sessions:
        - Uses Nairobi time
        - At/after 06:00 Nairobi time, automatically clocks out ALL present users' OVERTIME sessions only
        - Ignores WorkingHoursConfig end_time entirely
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            # Current Kenya time
            now = timezone.now().astimezone(KENYA_TZ)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Auto clock-out overtime job started at {now_str}")

            # Hard cutoff time: 06:00 Nairobi time (today)
            cutoff_time = dt.time(6, 0, 0)
            cutoff_dt = dt.datetime.combine(now.date(), cutoff_time)
            if timezone.is_naive(cutoff_dt):
                cutoff_dt = KENYA_TZ.localize(cutoff_dt)

            Logs.atuta_logger(f"[INFO] Overtime auto clock-out cutoff set to {cutoff_dt}")

            # If it's not yet 06:00 Nairobi time, skip the entire run
            if now < cutoff_dt:
                Logs.atuta_logger(
                    f"[SKIP] Not yet overtime cutoff time. Now={now} | Cutoff={cutoff_dt}"
                )
                print(f"[INFO] Auto clock-out overtime job finished at {now_str}")
                return

            # Only active users who are present today
            users = CustomUser.objects.filter(is_active=True, is_present_today=True)

            total_users = users.count()
            clocked_out = 0
            skipped_no_session = 0

            for user in users:
                try:
                    Logs.atuta_logger(
                        f"[EVALUATE] User {user.user_id} ({user.full_name}) | Now={now} | Cutoff={cutoff_dt}"
                    )

                    # Always attempt to clock out overtime sessions only
                    result = cls.clock_out_overtime_only(
                        user=user,
                        timestamp=now,
                        notes="Auto clock-out at 06:00 Nairobi time"
                    )

                    if result.get("status") == "success":
                        clocked_out += 1
                        Logs.atuta_logger(
                            f"[CLOCKED_OUT] Overtime | User {user.user_id} ({user.full_name})"
                        )
                    else:
                        skipped_no_session += 1
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — no open overtime session"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto overtime clock-out failed for user {user.user_id}",
                        exc_info=inner_exc
                    )

            # Summary
            Logs.atuta_logger(
                f"[SUMMARY] Overtime | Total users evaluated: {total_users} | "
                f"Clocked out: {clocked_out} | "
                f"Skipped (no overtime session): {skipped_no_session}"
            )
            print(f"[INFO] Auto clock-out overtime job finished at {now_str}")

        except Exception as e:
            Logs.atuta_technical_logger(
                "Critical error in AttendanceService.auto_clock_out_overtime_users",
                exc_info=e
            )
            raise

    @classmethod
    def auto_clock_out_overtime_users_dep(cls):
        """
        Loop through all active users who are currently present, evaluate their end-of-day
        using Nairobi time, and automatically clock out regular sessions only.
        Detailed logs for evaluation, skipped users, and clocked-out users.
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            # Current Kenya time
            now = timezone.now().astimezone(KENYA_TZ)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Auto clock-out job started at {now_str}")

            # Only active users who are present today
            users = CustomUser.objects.filter(
                is_active=True,
                is_present_today=True
            )

            total_users = users.count()
            clocked_out = 0
            skipped_no_session = 0
            skipped_no_config = 0

            for user in users:
                try:
                    # Get today's end time for this user
                    day_config = cls.get_user_day_end_time(user.user_id)

                    if not day_config or not day_config.get("end_time"):
                        skipped_no_config += 1
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — no working hours config today"
                        )
                        continue

                    end_time = day_config["end_time"]

                    # Combine today's date with end_time and localize to Nairobi
                    end_datetime = dt.datetime.combine(now.date(), end_time)
                    if timezone.is_naive(end_datetime):
                        end_datetime = KENYA_TZ.localize(end_datetime)

                    Logs.atuta_logger(
                        f"[EVALUATE] User {user.user_id} ({user.full_name}) | "
                        f"Now={now} | End_of_day={end_datetime}"
                    )

                    # Only clock out if current Kenya time >= configured end time
                    if now >= end_datetime:
                        result = cls.clock_out_overtime_only(
                            user=user,
                            timestamp=now,
                            notes="Auto clock-out at end of working hours"
                        )

                        if result.get("status") == "success":
                            clocked_out += 1
                            Logs.atuta_logger(
                                f"[CLOCKED_OUT] User {user.user_id} ({user.full_name})"
                            )
                        else:
                            skipped_no_session += 1
                            Logs.atuta_logger(
                                f"[SKIP] User {user.user_id} ({user.full_name}) — no open regular session"
                            )
                    else:
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — not yet end-of-day"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto clock-out failed for user {user.user_id}",
                        exc_info=inner_exc
                    )

            # Summary
            Logs.atuta_logger(
                f"[SUMMARY] Total users evaluated: {total_users} | "
                f"Clocked out: {clocked_out} | "
                f"Skipped (no regular session): {skipped_no_session} | "
                f"Skipped (no config): {skipped_no_config}"
            )
            print(f"[INFO] Auto clock-out job finished at {now_str}")

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.auto_clock_out_users_at_day_end",
                exc_info=e
            )
            raise e

    @classmethod
    def auto_clock_out_users_at_day_end(cls):
        """
        Auto clock-out job:
        - Uses Nairobi time
        - At/after 19:00 Nairobi time, automatically clocks out ALL present users (regular sessions only)
        - Uses 19:00 as ANCHOR time for calculations (even if cron runs later)
        - Calculates hours between configured end_time and 19:00 anchor time
        - Records a NEGATIVE hour correction to subtract those hours
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            # Current Kenya time
            now = timezone.now().astimezone(KENYA_TZ)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Auto clock-out job started at {now_str}")

            # Hard cutoff time: 19:00 Nairobi time (today) => this is the ANCHOR
            cutoff_time = dt.time(19, 0, 0)
            cutoff_dt = dt.datetime.combine(now.date(), cutoff_time)
            if timezone.is_naive(cutoff_dt):
                cutoff_dt = KENYA_TZ.localize(cutoff_dt)

            Logs.atuta_logger(f"[INFO] Auto clock-out cutoff/anchor set to {cutoff_dt}")

            # If it's not yet 19:00 Nairobi time, skip the entire run
            if now < cutoff_dt:
                Logs.atuta_logger(
                    f"[SKIP] Not yet cutoff time. Now={now} | Cutoff={cutoff_dt}"
                )
                print(f"[INFO] Auto clock-out job finished at {now_str}")
                return

            # Only active users who are present today
            users = CustomUser.objects.filter(is_active=True, is_present_today=True)

            total_users = users.count()
            clocked_out = 0
            skipped_no_session = 0
            corrections_recorded = 0
            corrections_skipped = 0

            for user in users:
                try:
                    Logs.atuta_logger(
                        f"[EVALUATE] User {user.user_id} ({user.full_name}) | Now={now} | Anchor={cutoff_dt}"
                    )

                    # Always attempt to clock out regular sessions only
                    # IMPORTANT: We pass ANCHOR (19:00) as the timestamp for the clock out.
                    result = cls.clock_out_regular_only(
                        user=user,
                        timestamp=cutoff_dt,
                        notes="Auto clock-out at 19:00 Nairobi time"
                    )

                    if result.get("status") == "success":
                        clocked_out += 1
                        Logs.atuta_logger(
                            f"[CLOCKED_OUT] User {user.user_id} ({user.full_name})"
                        )

                        # After successful clock-out, calculate hours between configured end_time and ANCHOR (19:00)
                        diff_res = cls.get_hours_between_end_time_and_anchor(
                            user_id=user.user_id,
                            anchor_time=cutoff_dt
                        )

                        if diff_res and diff_res.get("status") == "success":
                            hours_to_deduct = diff_res.get("hours", 0)

                            # Only record correction if there's something to deduct
                            if hours_to_deduct and float(hours_to_deduct) > 0:
                                correction_result = PayrollService.record_hour_correction(
                                    user=user,
                                    hours=-float(hours_to_deduct),  # NEGATIVE to subtract
                                    reason="Auto correction: deducted hours between configured end time and 19:00 auto clock-out",
                                    corrected_by=None,
                                    month=cutoff_dt.month,
                                    year=cutoff_dt.year,
                                )

                                if correction_result.get("status") == "success":
                                    corrections_recorded += 1
                                    Logs.atuta_logger(
                                        f"[CORRECTION_RECORDED] User {user.user_id} ({user.full_name}) | "
                                        f"hours_deducted=-{hours_to_deduct} | anchor={cutoff_dt}"
                                    )
                                else:
                                    corrections_skipped += 1
                                    Logs.atuta_logger(
                                        f"[CORRECTION_FAILED] User {user.user_id} ({user.full_name}) | "
                                        f"hours_to_deduct={hours_to_deduct} | message={correction_result.get('message')}"
                                    )
                            else:
                                corrections_skipped += 1
                                Logs.atuta_logger(
                                    f"[CORRECTION_SKIP] User {user.user_id} ({user.full_name}) | nothing to deduct (hours={hours_to_deduct})"
                                )
                        else:
                            corrections_skipped += 1
                            Logs.atuta_logger(
                                f"[CORRECTION_SKIP] User {user.user_id} ({user.full_name}) | could not compute hours to deduct"
                            )

                    else:
                        skipped_no_session += 1
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — no open regular session"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto clock-out failed for user {user.user_id}",
                        exc_info=inner_exc
                    )

            # Summary
            Logs.atuta_logger(
                f"[SUMMARY] Total users evaluated: {total_users} | "
                f"Clocked out: {clocked_out} | "
                f"Skipped (no regular session): {skipped_no_session} | "
                f"Corrections recorded: {corrections_recorded} | "
                f"Corrections skipped/failed: {corrections_skipped}"
            )
            print(f"[INFO] Auto clock-out job finished at {now_str}")

        except Exception as e:
            Logs.atuta_technical_logger(
                "Critical error in AttendanceService.auto_clock_out_users_at_day_end",
                exc_info=e
            )
            raise

    @classmethod
    def auto_clock_out_users_at_day_end_dep(cls):
        """
        Auto clock-out job:
        - Uses Nairobi time
        - At/after 19:00 Nairobi time, automatically clocks out ALL present users (regular sessions only)
        - Ignores WorkingHoursConfig end_time entirely
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            # Current Kenya time
            now = timezone.now().astimezone(KENYA_TZ)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Auto clock-out job started at {now_str}")

            # Hard cutoff time: 19:00 Nairobi time (today)
            cutoff_time = dt.time(19, 0, 0)
            cutoff_dt = dt.datetime.combine(now.date(), cutoff_time)
            if timezone.is_naive(cutoff_dt):
                cutoff_dt = KENYA_TZ.localize(cutoff_dt)

            Logs.atuta_logger(f"[INFO] Auto clock-out cutoff set to {cutoff_dt}")

            # If it's not yet 19:00 Nairobi time, skip the entire run
            if now < cutoff_dt:
                Logs.atuta_logger(
                    f"[SKIP] Not yet cutoff time. Now={now} | Cutoff={cutoff_dt}"
                )
                print(f"[INFO] Auto clock-out job finished at {now_str}")
                return

            # Only active users who are present today
            users = CustomUser.objects.filter(is_active=True, is_present_today=True)

            total_users = users.count()
            clocked_out = 0
            skipped_no_session = 0

            for user in users:
                try:
                    Logs.atuta_logger(
                        f"[EVALUATE] User {user.user_id} ({user.full_name}) | Now={now} | Cutoff={cutoff_dt}"
                    )

                    # Always attempt to clock out regular sessions only
                    result = cls.clock_out_regular_only(
                        user=user,
                        timestamp=now,
                        notes="Auto clock-out at 19:00 Nairobi time"
                    )

                    if result.get("status") == "success":
                        clocked_out += 1
                        Logs.atuta_logger(
                            f"[CLOCKED_OUT] User {user.user_id} ({user.full_name})"
                        )
                    else:
                        skipped_no_session += 1
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — no open regular session"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto clock-out failed for user {user.user_id}",
                        exc_info=inner_exc
                    )

            # Summary
            Logs.atuta_logger(
                f"[SUMMARY] Total users evaluated: {total_users} | "
                f"Clocked out: {clocked_out} | "
                f"Skipped (no regular session): {skipped_no_session}"
            )
            print(f"[INFO] Auto clock-out job finished at {now_str}")

        except Exception as e:
            Logs.atuta_technical_logger(
                "Critical error in AttendanceService.auto_clock_out_users_at_day_end",
                exc_info=e
            )
            raise

    @classmethod
    def auto_clock_out_users_at_day_end_dep(cls):
        """
        Loop through all active users who are currently present, evaluate their end-of-day
        using Nairobi time, and automatically clock out regular sessions only.
        Detailed logs for evaluation, skipped users, and clocked-out users.
        """
        KENYA_TZ = pytz.timezone("Africa/Nairobi")

        try:
            # Current Kenya time
            now = timezone.now().astimezone(KENYA_TZ)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Auto clock-out job started at {now_str}")

            # Only active users who are present today
            users = CustomUser.objects.filter(
                is_active=True,
                is_present_today=True
            )

            total_users = users.count()
            clocked_out = 0
            skipped_no_session = 0
            skipped_no_config = 0

            for user in users:
                try:
                    # Get today's end time for this user
                    day_config = cls.get_user_day_end_time(user.user_id)

                    if not day_config or not day_config.get("end_time"):
                        skipped_no_config += 1
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — no working hours config today"
                        )
                        continue

                    end_time = day_config["end_time"]

                    # Combine today's date with end_time and localize to Nairobi
                    end_datetime = dt.datetime.combine(now.date(), end_time)
                    if timezone.is_naive(end_datetime):
                        end_datetime = KENYA_TZ.localize(end_datetime)

                    Logs.atuta_logger(
                        f"[EVALUATE] User {user.user_id} ({user.full_name}) | "
                        f"Now={now} | End_of_day={end_datetime}"
                    )

                    # Only clock out if current Kenya time >= configured end time
                    if now >= end_datetime:
                        result = cls.clock_out_regular_only(
                            user=user,
                            timestamp=now,
                            notes="Auto clock-out at end of working hours"
                        )

                        if result.get("status") == "success":
                            clocked_out += 1
                            Logs.atuta_logger(
                                f"[CLOCKED_OUT] User {user.user_id} ({user.full_name})"
                            )
                        else:
                            skipped_no_session += 1
                            Logs.atuta_logger(
                                f"[SKIP] User {user.user_id} ({user.full_name}) — no open regular session"
                            )
                    else:
                        Logs.atuta_logger(
                            f"[SKIP] User {user.user_id} ({user.full_name}) — not yet end-of-day"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto clock-out failed for user {user.user_id}",
                        exc_info=inner_exc
                    )

            # Summary
            Logs.atuta_logger(
                f"[SUMMARY] Total users evaluated: {total_users} | "
                f"Clocked out: {clocked_out} | "
                f"Skipped (no regular session): {skipped_no_session} | "
                f"Skipped (no config): {skipped_no_config}"
            )
            print(f"[INFO] Auto clock-out job finished at {now_str}")

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.auto_clock_out_users_at_day_end",
                exc_info=e
            )
            raise e

    @classmethod
    def get_user_day_end_time(cls, user_id):
        try:
            # Fetch user
            user = CustomUser.objects.get(user_id=user_id)

            # Server time (timezone-aware)
            now = timezone.localtime(timezone.now())

            # Django weekday: Monday=0 → Sunday=6
            day_of_week = now.weekday() + 1  # Convert to your 1–7 mapping

            # Fetch working hours config
            config = WorkingHoursConfig.objects.filter(
                user_role=user.user_role,
                day_of_week=day_of_week,
                is_active=True
            ).first()

            if not config:
                Logs.atuta_logger(
                    f"No working hours config found for role={user.user_role}, day={day_of_week}"
                )
                return None

            return {
                "day": day_of_week,
                "end_time": config.end_time,
                "timezone": config.timezone
            }

        except CustomUser.DoesNotExist:
            Logs.atuta_logger(f"User not found while fetching day end time: {user_id}")
            return None

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.get_user_day_end_time "
                f"for user {user_id}: {str(e)}"
            )
            raise e

    @staticmethod
    def get_user_hour_corrections(user_id, start_month, start_year, end_month, end_year):
        try:
            # --- DEBUG LOG 1: Inputs ---
            Logs.atuta_technical_logger(
                f"DEBUG: HourCorrection Request -> User: {user_id}, "
                f"Range: {start_month}/{start_year} to {end_month}/{end_year}"
            )

            if not user_id:
                return {"status": "error", "message": "User ID is required"}

            # Ensure inputs are integers for reliable comparison
            try:
                s_m, s_y = int(start_month), int(start_year)
                e_m, e_y = int(end_month), int(end_year)
            except (ValueError, TypeError):
                Logs.atuta_technical_logger("DEBUG: Failed to cast month/year to integers")
                return {"status": "error", "message": "Invalid date parameters"}

            # --- 2. Build the date range filter ---
            # Logic: (Year > StartYear OR (Year == StartYear AND Month >= StartMonth)) 
            # AND (Year < EndYear OR (Year == EndYear AND Month <= EndMonth))
            start_filter = Q(year__gt=s_y) | Q(year=s_y, month__gte=s_m)
            end_filter = Q(year__lt=e_y) | Q(year=e_y, month__lte=e_m)

            # --- 3. Fetch records (Fixed .order_by) ---
            queryset = HourCorrection.objects.filter(
                user_id=user_id
            ).filter(
                start_filter & end_filter
            ).select_related('corrected_by').order_by('-date', '-created_at')

            # --- DEBUG LOG 2: Query Result ---
            count = queryset.count()
            Logs.atuta_technical_logger(f"DEBUG: Found {count} records in database for this filter.")

            # 4. Format data for the frontend
            corrections_list = []
            total_adjustment_amount = Decimal('0.00')
            total_hours = Decimal('0.00')

            for record in queryset:
                corrections_list.append({
                    "correction_id": str(record.correction_id),
                    "date": record.date.strftime("%Y-%m-%d") if record.date else "",
                    "display_period": f"{record.month}/{record.year}",
                    "hours": float(record.hours),
                    "hourly_rate": float(record.hourly_rate) if record.hourly_rate else 0,
                    "amount": float(record.amount),
                    "reason": record.reason,
                    "corrected_by": record.corrected_by.full_name if record.corrected_by else "System",
                    "created_at": record.created_at.strftime("%Y-%m-%d %H:%M")
                })
                total_adjustment_amount += record.amount
                total_hours += record.hours

            return {
                "status": "success",
                "data": {
                    "records": corrections_list,
                    "summary": {
                        "total_count": len(corrections_list),
                        "total_hours": float(total_hours),
                        "total_amount": float(total_adjustment_amount)
                    }
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"CRITICAL ERROR in HourCorrectionService: {str(e)}")
            return {
                "status": "error", 
                "message": "Internal server error while fetching hour corrections"
            }

    @classmethod
    def get_detailed_attendance_report(cls, user_id, start_date, end_date):
        try:
            # Fetch User details
            user = CustomUser.objects.get(user_id=user_id)

            # Perform conditional aggregation for top summary cards
            stats = AttendanceSession.objects.filter(
                user=user,
                date__range=[start_date, end_date]
            ).aggregate(
                reg_hours=Sum(Case(When(clockin_type='regular', then='total_hours'), output_field=DecimalField())),
                ot_hours=Sum(Case(When(clockin_type='overtime', then='total_hours'), output_field=DecimalField())),
                grand_total=Sum('total_hours')
            )

            # Fetch sessions ordered by date descending
            sessions = AttendanceSession.objects.filter(
                user=user,
                date__range=[start_date, end_date]
            ).order_by('-date', 'clock_in_time')

            daily_data = {}
            for s in sessions:
                # Grouping key format: "Fri 31/10"
                date_key = s.date.strftime("%a %d/%m")
                
                if date_key not in daily_data:
                    daily_data[date_key] = {
                        "date_display": date_key,
                        "day_total": 0,
                        "sessions": []
                    }
                
                hours = float(s.total_hours or 0)
                daily_data[date_key]["day_total"] += hours
                daily_data[date_key]["sessions"].append({
                    "session_id": str(s.session_id),
                    "type": s.get_clockin_type_display(),
                    "clock_in": s.clock_in_time,
                    "clock_out": s.clock_out_time,
                    "hours": hours,
                    "status": s.status
                })

            return {
                "user": {
                    "full_name": user.full_name,
                    "photo": user.photo.url if user.photo else None,
                },
                "summary": {
                    "work_hours": stats['grand_total'] or 0,
                    "regular": stats['reg_hours'] or 0,
                    "overtime": stats['ot_hours'] or 0,
                },
                "rows": list(daily_data.values())
            }

        except CustomUser.DoesNotExist:
            Logs.atuta_logger(f"Report failure: User ID {user_id} not found.")
            return None
        except Exception as e:
            Logs.atuta_technical_logger(f"Critical error in AttendanceService.get_detailed_attendance_report for User {user_id}: {str(e)}")
            raise e

    @classmethod
    def get_attendance_history(cls, start_date=None, end_date=None, user_id=None, page=1, page_size=50):
        """
        Returns attendance sessions with date range filtering + pagination.
        If user_id is provided, filters for that specific user.
        If user_id is None, returns records for all users (Admin view).

        Response shape (frontend-friendly):
        {
        "status": "success",
        "data": {
            "results": [...],
            "pagination": {...}
        }
        }
        """
        try:
            # 1) Base Queryset (optimized)
            sessions = AttendanceSession.objects.select_related("user")

            # 2) Filter by user (optional)
            if user_id:
                sessions = sessions.filter(user__user_id=user_id)

            # 3) Date range filters
            if start_date:
                sessions = sessions.filter(date__gte=start_date)
            if end_date:
                sessions = sessions.filter(date__lte=end_date)

            # 4) Ordering
            sessions = sessions.order_by("-date", "-created_at")

            # 5) Pagination parsing/safety
            try:
                page = int(page) if page is not None else 1
            except (TypeError, ValueError):
                page = 1

            try:
                page_size = int(page_size) if page_size is not None else 50
            except (TypeError, ValueError):
                page_size = 50

            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 50
            if page_size > 500:
                page_size = 500

            paginator = Paginator(sessions, page_size)

            try:
                page_obj = paginator.page(page)
            except PageNotAnInteger:
                page = 1
                page_obj = paginator.page(page)
            except EmptyPage:
                page = paginator.num_pages if paginator.num_pages > 0 else 1
                page_obj = paginator.page(page)

            results = []

            for session in page_obj.object_list:
                # Safe photo url
                try:
                    clock_in_photo_url = session.clock_in_photo.url if session.clock_in_photo else None
                except Exception:
                    clock_in_photo_url = None

                results.append({
                    "session_id": str(session.session_id),
                    "user_id": str(session.user.user_id),
                    "full_name": session.user.full_name,

                    "date": session.date.isoformat() if session.date else None,
                    "clock_in_time": session.clock_in_time.isoformat() if session.clock_in_time else None,
                    "lunch_in": session.lunch_in.isoformat() if session.lunch_in else None,
                    "lunch_out": session.lunch_out.isoformat() if session.lunch_out else None,
                    "clock_out_time": session.clock_out_time.isoformat() if session.clock_out_time else None,

                    "clockin_type": session.clockin_type,
                    "total_hours": str(session.total_hours) if session.total_hours is not None else None,
                    "status": session.status,
                    "notes": session.notes,
                    "clock_in_photo_url": clock_in_photo_url,
                })

            Logs.atuta_logger(
                f"Attendance history fetched (paginated): range {start_date} to {end_date} | "
                f"user={user_id or 'ALL'} | page={page} | page_size={page_size} | total={paginator.count}"
            )

            return {
                "status": "success",
                "data": {
                    "results": results,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_pages": paginator.num_pages,
                        "total_records": paginator.count,
                        "has_next": page_obj.has_next(),
                        "has_previous": page_obj.has_previous(),
                    }
                },
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_attendance_history_failed", exc_info=e)
            return {"status": "error", "message": "attendance_history_fetch_failed"}

    @classmethod
    def get_user_attendance_history(cls, user_id, start_date=None, end_date=None):
        """
        Returns attendance sessions for a user.
        Optional date filters:
            start_date, end_date -> filter by date range
        """
        try:
            sessions = AttendanceSession.objects.filter(user__user_id=user_id)

            # Optional filtering
            if start_date:
                sessions = sessions.filter(date__gte=start_date)
            if end_date:
                sessions = sessions.filter(date__lte=end_date)

            sessions = sessions.select_related("user").order_by("-date", "-created_at")

            data = []

            for session in sessions:

                try:
                    clock_in_photo_url = session.clock_in_photo.url if session.clock_in_photo else None
                except Exception:
                    clock_in_photo_url = None

                data.append({
                    "session_id": str(session.session_id),
                    "date": session.date,
                    "clock_in_time": session.clock_in_time,
                    "lunch_in": session.lunch_in,
                    "lunch_out": session.lunch_out,
                    "clock_out_time": session.clock_out_time,
                    "total_hours": session.total_hours,
                    "status": session.status,
                    "notes": session.notes,
                    "clock_in_photo_url": clock_in_photo_url,
                })

            return {
                "status": "success",
                "message": data,
            }

        except Exception:
            return {
                "status": "error",
                "message": "user_attendance_fetch_failed",
            }


    @classmethod
    def get_today_user_time_summary(cls):
        """
        For each user with attendance activity today:
        - earliest clock in
        - latest clock out (or 'open')
        - total hours worked across all sessions
        - user photo URL
        - clock-in photo URL of latest session
        - user role
        - latest session status (open/closed)
        """
        try:
            today = timezone.localdate()

            # Pull today's sessions, ordered by user and clock_in_time for processing
            sessions = (
                AttendanceSession.objects
                .filter(date=today, clock_in_time__isnull=False) # Only sessions with a clock-in time
                .select_related("user")
                .order_by("user", "clock_in_time") 
            )

            user_map = {}

            for session in sessions:
                user = session.user
                uid = user.user_id

                if uid not in user_map:
                    # Initialize entry (Same as before)
                    try:
                        user_photo_url = user.photo.url if user.photo else None
                    except Exception:
                        user_photo_url = None

                    user_map[uid] = {
                        "user_id": str(uid),
                        "full_name": user.full_name,
                        "email": user.email,
                        "user_role": user.user_role,
                        "user_photo_url": user_photo_url,
                        "earliest_clock_in": session.clock_in_time, # Initialize with first session's clock_in
                        # Use a timestamp for comparison
                        "latest_timestamp": session.clock_in_time, 
                        "latest_clock_out": None,
                        "total_hours_worked": Decimal("0.00"),
                        "latest_clock_in_photo_url": None,
                        "latest_session_status": None,
                    }

                entry = user_map[uid]

                # 1. Earliest clock-in (Always simple comparison)
                if session.clock_in_time and session.clock_in_time < entry["earliest_clock_in"]:
                    entry["earliest_clock_in"] = session.clock_in_time

                # 2. Total hours calculation (Same as before)
                if session.clock_in_time and session.clock_out_time:
                    diff = session.clock_out_time - session.clock_in_time
                    hours = Decimal(diff.total_seconds()) / Decimal(3600)
                    entry["total_hours_worked"] += hours.quantize(Decimal("0.01"))
                
                # --- CRITICAL FIX START ---

                # 3. Determine the latest activity timestamp for this session
                current_latest_time = session.clock_out_time or session.clock_in_time

                if current_latest_time and current_latest_time >= entry["latest_timestamp"]:
                    entry["latest_timestamp"] = current_latest_time
                    
                    # Update status, clock-out, and photo details based on the NEWEST session
                    entry["latest_session_status"] = session.status
                    entry["latest_clock_out"] = session.clock_out_time # Can be None if open

                    try:
                        entry["latest_clock_in_photo_url"] = session.clock_in_photo.url if session.clock_in_photo else None
                    except Exception:
                        entry["latest_clock_in_photo_url"] = None

                # --- CRITICAL FIX END ---

            # 4. Final formatting: Replace None with 'open'
            for entry in user_map.values():
                if entry["latest_clock_out"] is None and entry["latest_session_status"] == 'open':
                    entry["latest_clock_out"] = "open"

            data = list(user_map.values())

            # Logs.atuta_logger(f"Today's attendance summary generated for {len(data)} users")

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            # Logs.atuta_technical_logger("get_today_user_time_summary_failed", exc_info=e)
            return {
                "status": "error",
                "message": "attendance_summary_failed",
            }


    @classmethod
    def clock_in(cls, user, timestamp, clockin_type="regular", photo_base64: str = None):
        """
        Create a new attendance session for a user.
        Now supports clockin_type: 'regular' or 'overtime'.

        FIXED:
        - check_lateness() is executed BEFORE creating the AttendanceSession
        so it can correctly detect FIRST vs SECOND session.
        - Lateness check never blocks clock-in; failures are logged and ignored.
        """
        try:
            if timestamp is None:
                return {"status": "error", "message": "missing_timestamp"}

            if user.is_on_leave:
                return {"status": "error", "message": "user_on_leave"}

            # Validate clockin_type
            valid_types = [choice[0] for choice in AttendanceSession.CLOCKIN_TYPE_CHOICES]
            if clockin_type not in valid_types:
                return {"status": "error", "message": "invalid_clockin_type"}

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            # ✅ Run lateness check BEFORE session creation
            lateness_result = None
            try:
                lateness_result = cls.check_lateness(user=user, timestamp=timestamp)
            except Exception as e:
                Logs.atuta_technical_logger(
                    f"check_lateness_failed_before_clock_in_user_{user.user_id}",
                    exc_info=e
                )
                lateness_result = {"status": "error", "message": "check_lateness_failed"}

            with transaction.atomic():
                # Ensure no active session for this user
                existing = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    status="open",
                    clock_out_time__isnull=True
                ).first()

                if existing:
                    return {"status": "error", "message": "active_session_exists"}

                attendance_data = {
                    "user": user,
                    # ✅ Use the same date basis as lateness check expects (Nairobi date)
                    # If you want to keep the old behavior (timestamp.date()), revert this line.
                    "date": timezone.localtime(timestamp).date(),
                    "clock_in_time": timestamp,
                    "clockin_type": clockin_type,
                    "status": "open",
                }

                if photo_base64:
                    try:
                        if ";base64," in photo_base64:
                            format_part, imgstr = photo_base64.split(";base64,")
                            ext = format_part.split("/")[-1]
                        else:
                            imgstr = photo_base64
                            ext = "jpg"

                        decoded = base64.b64decode(imgstr)
                        file = ContentFile(decoded, name=f"{uuid.uuid4()}.{ext}")
                        attendance_data["clock_in_photo"] = file
                    except Exception as e:
                        Logs.atuta_technical_logger(
                            f"clock_in_photo_save_failed_user_{user.user_id}",
                            exc_info=e
                        )
                        return {"status": "error", "message": "invalid_photo_data"}

                # Create attendance session
                session = AttendanceSession.objects.create(**attendance_data)

                # Mark user as present today
                if not user.is_present_today:
                    user.is_present_today = True
                    user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(
                f"User clocked in | type={clockin_type} | user={user.user_id} | session_id={session.session_id}"
            )

            response = {
                "status": "success",
                "message": "clock_in_recorded",
                "session_id": str(session.session_id),
                "clockin_type": clockin_type,
            }

            if lateness_result:
                response["lateness"] = lateness_result

            return response

        except Exception as e:
            Logs.atuta_technical_logger(f"clock_in_failed_user_{user.user_id}", exc_info=e)
            return {"status": "error", "message": "clock_in_failed"}

    @classmethod
    def clock_out_overtime_only(cls, user, timestamp: datetime.datetime, notes: str = None):
        """
        Clock out the current open session, mark status as 'closed', optionally save notes,
        and update user's is_present_today to False.
        """
        try:
            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            with transaction.atomic():
                session = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    clockin_type='overtime',
                    status="open",
                    clock_out_time__isnull=True
                ).first()

                if not session:
                    return {"status": "error", "message": "no_active_session"}

                session.clock_out_time = timestamp
                session.status = "closed"

                # Save optional notes
                if notes:
                    session.notes = notes

                # Calculate total hours
                delta = session.clock_out_time - session.clock_in_time
                session.total_hours = round(delta.total_seconds() / 3600, 2)

                session.save()

                # Update user's present status
                user.is_present_today = False
                user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(
                f"User clocked out | user={user.user_id} | session_id={session.session_id}"
            )

            return {"status": "success", "message": "clock_out_recorded"}

        except Exception as e:
            Logs.atuta_technical_logger(
                f"clock_out_failed_user_{user.user_id}", exc_info=e
            )
            return {"status": "error", "message": "clock_out_failed"}

    @classmethod
    def clock_out_regular_only(cls, user, timestamp: datetime.datetime, notes: str = None):
        """
        Clock out the current open session, mark status as 'closed', optionally save notes,
        and update user's is_present_today to False.
        """
        try:
            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            with transaction.atomic():
                session = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    clockin_type='regular',
                    status="open",
                    clock_out_time__isnull=True
                ).first()

                if not session:
                    return {"status": "error", "message": "no_active_session"}

                session.clock_out_time = timestamp
                session.status = "closed"

                # Save optional notes
                if notes:
                    session.notes = notes

                # Calculate total hours
                delta = session.clock_out_time - session.clock_in_time
                session.total_hours = round(delta.total_seconds() / 3600, 2)

                session.save()

                # Update user's present status
                user.is_present_today = False
                user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(
                f"User clocked out | user={user.user_id} | session_id={session.session_id}"
            )

            return {"status": "success", "message": "clock_out_recorded"}

        except Exception as e:
            Logs.atuta_technical_logger(
                f"clock_out_failed_user_{user.user_id}", exc_info=e
            )
            return {"status": "error", "message": "clock_out_failed"}

    @classmethod
    def clock_out(cls, user, timestamp: datetime.datetime, notes: str = None, photo_base64: str = None):
        """
        Clock out the current open session, mark status as 'closed', optionally save notes + clock-out photo,
        and update user's is_present_today to False.
        """
        try:
            if timestamp is None:
                return {"status": "error", "message": "missing_timestamp"}

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            with transaction.atomic():
                session = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    status="open",
                    clock_out_time__isnull=True
                ).first()

                if not session:
                    return {"status": "error", "message": "no_active_session"}

                session.clock_out_time = timestamp
                session.status = "closed"

                # Save optional notes
                if notes:
                    session.notes = notes

                # Save optional clock-out photo (same pattern as clock_in)
                if photo_base64:
                    try:
                        if ";base64," in photo_base64:
                            format_part, imgstr = photo_base64.split(";base64,")
                            ext = format_part.split("/")[-1]
                        else:
                            imgstr = photo_base64
                            ext = "jpg"

                        decoded = base64.b64decode(imgstr)
                        file = ContentFile(decoded, name=f"{uuid.uuid4()}.{ext}")
                        session.clock_out_photo = file
                    except Exception as e:
                        Logs.atuta_technical_logger(
                            f"clock_out_photo_save_failed_user_{user.user_id}",
                            exc_info=e
                        )
                        return {"status": "error", "message": "invalid_photo_data"}

                # Calculate total hours
                delta = session.clock_out_time - session.clock_in_time
                session.total_hours = round(delta.total_seconds() / 3600, 2)

                session.save()

                # Update user's present status
                user.is_present_today = False
                user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(
                f"User clocked out | user={user.user_id} | session_id={session.session_id}"
            )

            return {"status": "success", "message": "clock_out_recorded"}

        except Exception as e:
            Logs.atuta_technical_logger(
                f"clock_out_failed_user_{user.user_id}", exc_info=e
            )
            return {"status": "error", "message": "clock_out_failed"}

        
    @classmethod
    def get_current_session(cls, user):
        """
        Retrieve the user's current active attendance session (status=open).
        """
        try:
            with transaction.atomic():
                session = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    status="open"
                ).first()

                if not session:
                    return {"status": "error", "message": "no_active_session"}

            # Serialize session data for frontend
            session_data = {
                "session_id": str(session.session_id),
                "clock_in_time": session.clock_in_time.isoformat(),
                "clockin_type": session.clockin_type,
                "clock_in_photo": session.clock_in_photo.url if session.clock_in_photo else None,
                "notes": session.notes,
                "total_hours": session.total_hours,
                "status": session.status,
            }

            Logs.atuta_technical_logger(
                f"Retrieved current session | user={user.user_id} | session_id={session.session_id}"
            )

            return {"status": "success", "session": session_data}

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_current_session_failed_user_{user.user_id}", exc_info=e
            )
            return {"status": "error", "message": "get_current_session_failed"}



    @classmethod
    def lunch_in(cls, user, timestamp: datetime.datetime):
        try:
            session = AttendanceSession.objects.filter(
                user=user,
                clock_in_time__isnull=False,
                clock_out_time__isnull=False,
                lunch_in__isnull=True
            ).last()

            if not session:
                return {
                    "status": "error",
                    "message": "no_session_available"
                }

            session.lunch_in = timestamp
            session.save()

            return {
                "status": "success",
                "message": "lunch_in_recorded"
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"lunch_in_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "lunch_in_failed"
            }


    @classmethod
    def lunch_out(cls, user, timestamp: datetime.datetime):
        try:
            session = AttendanceSession.objects.filter(
                user=user,
                lunch_in__isnull=False,
                lunch_out__isnull=True
            ).last()

            if not session:
                return {
                    "status": "error",
                    "message": "no_lunch_session"
                }

            session.lunch_out = timestamp
            session.save()

            return {
                "status": "success",
                "message": "lunch_out_recorded"
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"lunch_out_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "lunch_out_failed"
            }


    @classmethod
    def calculate_total_hours(cls, attendance_session: AttendanceSession):
        """
        Pure calculation function
        """
        try:
            if not attendance_session.clock_in_time or not attendance_session.clock_out_time:
                return {
                    "status": "error",
                    "message": "incomplete_session"
                }

            total = attendance_session.clock_out_time - attendance_session.clock_in_time

            if attendance_session.lunch_in and attendance_session.lunch_out:
                total -= (attendance_session.lunch_out - attendance_session.lunch_in)

            return {
                "status": "success",
                "message": {
                    "total_hours": total
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger("total_hours_calc_failed", exc_info=e)
            return {
                "status": "error",
                "message": "total_hours_calc_failed"
            }
