from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import datetime
import base64
import uuid
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

from mapp.models import AttendanceSession
from mapp.classes.logs.logs import Logs


class AttendanceService:

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
    def clock_in(cls, user, timestamp, photo_base64: str = None):
        """
        Create a new attendance session for a user.
        Each clock-in creates a new record with status 'open'.
        Users on leave cannot clock in.
        Updates user's is_present_today to True on successful clock-in.
        """
        try:
            if timestamp is None:
                return {"status": "error", "message": "missing_timestamp"}

            if user.is_on_leave:
                return {"status": "error", "message": "user_on_leave"}

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            with transaction.atomic():
                # Ensure no active session
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

                # Mark user as present today
                user.is_present_today = True
                user.save(update_fields=["is_present_today"])

            Logs.atuta_technical_logger(f"User clocked in | user={user.user_id} | session_id={session.session_id}")

            return {
                "status": "success",
                "message": "clock_in_recorded",
                "session_id": str(session.session_id)
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
            Logs.error(f"lunch_in_failed_user_{user.user_id}", exc_info=e)
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
            Logs.error(f"lunch_out_failed_user_{user.user_id}", exc_info=e)
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
            Logs.error("total_hours_calc_failed", exc_info=e)
            return {
                "status": "error",
                "message": "total_hours_calc_failed"
            }
