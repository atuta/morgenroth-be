from django.db import transaction
from django.utils import timezone
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
    def clock_in(cls, user, timestamp, photo_base64: str = None):
        """
        Create a new attendance session for a user.
        Enforces single active session, safe timestamp, and safe photo handling.
        """
        try:
            # Normalize timestamp
            if timestamp is None:
                return {"status": "error", "message": "missing_timestamp"}

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp)

            with transaction.atomic():

                # Locking avoids the race condition
                existing = AttendanceSession.objects.select_for_update().filter(
                    user=user,
                    clock_in_time__isnull=False,
                    clock_out_time__isnull=True
                ).first()

                if existing:
                    return {"status": "error", "message": "active_session_exists"}

                attendance_data = {
                    "user": user,
                    "date": timestamp.date(),
                    "clock_in_time": timestamp
                }

                # Optional photo
                if photo_base64:
                    try:
                        # Handles both cases:
                        # data:image/png;base64,XXXXXXXX
                        # XXXXXXXXXXXX (raw base64 only)
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

                # Actually create session
                session = AttendanceSession.objects.create(**attendance_data)

            Logs.atuta_logger(f"User clocked in | user={user.user_id} | {timestamp}")

            return {
                "status": "success",
                "message": "clock_in_recorded",
                "session_id": str(session.session_id)
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"clock_in_failed_user_{user.user_id}", exc_info=e)
            return {"status": "error", "message": "clock_in_failed"}


    @classmethod
    def clock_out(cls, user, timestamp: datetime.datetime):
        try:
            session = AttendanceSession.objects.filter(
                user=user,
                clock_in_time__isnull=False,
                clock_out_time__isnull=True
            ).first()

            if not session:
                return {
                    "status": "error",
                    "message": "no_active_session"
                }

            session.clock_out_time = timestamp
            session.save()

            return {
                "status": "success",
                "message": "clock_out_recorded"
            }

        except Exception as e:
            Logs.error(f"clock_out_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "clock_out_failed"
            }


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
