from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum, Q, Case, When, DecimalField
from datetime import datetime
import datetime
import base64
import uuid
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

from mapp.models import AttendanceSession, CustomUser, HourCorrection, WorkingHoursConfig
from mapp.classes.logs.logs import Logs


class AttendanceService:

    @classmethod
    def auto_clock_out_users_at_day_end(cls):
        """
        Loop through all users and automatically clock them out
        if current server time has passed their configured end-of-day time.
        """
        try:
            now = timezone.localtime(timezone.now())

            users = CustomUser.objects.filter(
                is_active=True,
                is_present_today=True
            )

            for user in users:
                try:
                    # Get configured end time for today
                    day_config = cls.get_user_day_end_time(user.user_id)

                    if not day_config:
                        continue

                    end_time = day_config.get("end_time")
                    if not end_time:
                        continue

                    # Combine today's date with configured end_time
                    end_datetime = datetime.combine(
                        now.date(),
                        end_time
                    )

                    if timezone.is_naive(end_datetime):
                        end_datetime = timezone.make_aware(end_datetime)

                    # Only clock out if current time >= configured end time
                    if now >= end_datetime:
                        cls.clock_out(
                            user=user,
                            timestamp=now,
                            notes="Auto clock-out at end of working hours"
                        )

                except Exception as inner_exc:
                    Logs.atuta_technical_logger(
                        f"Auto clock-out failed for user {user.user_id}: {str(inner_exc)}"
                    )

        except Exception as e:
            Logs.atuta_technical_logger(
                f"Critical error in AttendanceService.auto_clock_out_users_at_day_end: {str(e)}"
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
    def get_attendance_history(cls, start_date=None, end_date=None, user_id=None):
        """
        Returns attendance sessions with date range filtering.
        If user_id is provided, filters for that specific user.
        If user_id is None, returns records for all users (Admin view).
        """
        try:
            # 1. Base Queryset with optimization
            sessions = AttendanceSession.objects.select_related("user")

            # 2. Filter by User if provided
            if user_id:
                sessions = sessions.filter(user__user_id=user_id)

            # 3. Date Range Filtering
            if start_date:
                sessions = sessions.filter(date__gte=start_date)
            if end_date:
                sessions = sessions.filter(date__lte=end_date)

            # 4. Ordering
            sessions = sessions.order_by("-date", "-created_at")

            data = []

            for session in sessions:
                # Handle photo URL safely
                try:
                    clock_in_photo_url = session.clock_in_photo.url if session.clock_in_photo else None
                except Exception:
                    clock_in_photo_url = None

                data.append({
                    "session_id": str(session.session_id),
                    "user_id": str(session.user.user_id),
                    "full_name": session.user.full_name,
                    "date": session.date,
                    "clock_in_time": session.clock_in_time,
                    "lunch_in": session.lunch_in,
                    "lunch_out": session.lunch_out,
                    "clock_out_time": session.clock_out_time,
                    "clockin_type": session.clockin_type,  # Added new field
                    "total_hours": session.total_hours,
                    "status": session.status,
                    "notes": session.notes,
                    "clock_in_photo_url": clock_in_photo_url, # Included as requested
                })

            # Log the successful fetch
            Logs.atuta_logger(f"Attendance history fetched: range {start_date} to {end_date} | user={user_id or 'ALL'}")

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            # Log technical details for debugging
            Logs.atuta_technical_logger(f"get_attendance_history_failed", exc_info=e)
            return {
                "status": "error",
                "message": "attendance_history_fetch_failed",
            }

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

            with transaction.atomic():
                # Ensure no active session for this specific type (or overall if preferred)
                # Logic: We check for ANY 'open' session for this user
                existing = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    status="open",
                    clock_out_time__isnull=True
                ).first()

                if existing:
                    return {"status": "error", "message": "active_session_exists"}

                attendance_data = {
                    "user": user,
                    "date": timestamp.date(),
                    "clock_in_time": timestamp,
                    "clockin_type": clockin_type,  # NEW
                    "status": "open"
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
                        Logs.atuta_technical_logger(f"clock_in_photo_save_failed_user_{user.user_id}", exc_info=e)
                        return {"status": "error", "message": "invalid_photo_data"}

                # Create attendance session
                session = AttendanceSession.objects.create(**attendance_data)

                # Mark user as present today (Only if it's a regular clock-in or always?)
                # Usually, if they are working overtime, they are also "present".
                if not user.is_present_today:
                    user.is_present_today = True
                    user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(
                f"User clocked in | type={clockin_type} | user={user.user_id} | session_id={session.session_id}"
            )

            return {
                "status": "success",
                "message": "clock_in_recorded",
                "session_id": str(session.session_id),
                "clockin_type": clockin_type
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"clock_in_failed_user_{user.user_id}", exc_info=e)
            return {"status": "error", "message": "clock_in_failed"}


    @classmethod
    def clock_out(cls, user, timestamp: datetime.datetime, notes: str = None):
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
