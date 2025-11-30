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
    def clock_in(cls, user, timestamp: datetime, photo_base64: str = None):
        """
        Clock in a user and optionally save a photo for verification.
        photo_base64: base64-encoded string of the image from camera
        """
        try:
            # Ensure no active session
            existing = AttendanceSession.objects.filter(
                user=user,
                clock_in_time__isnull=False,
                clock_out_time__isnull=True
            ).first()

            if existing:
                return {
                    "status": "error",
                    "message": "active_session_exists"
                }

            attendance_data = {
                "user": user,
                "date": timestamp.date(),
                "clock_in_time": timestamp
            }

            # Handle base64 photo if provided
            if photo_base64:
                try:
                    format, imgstr = photo_base64.split(';base64,')  # in case it has the prefix
                    ext = format.split('/')[-1]  # e.g., 'image/png'
                    photo_file = ContentFile(base64.b64decode(imgstr), name=f"{uuid.uuid4()}.{ext}")
                    attendance_data['clock_in_photo'] = photo_file
                except Exception as e:
                    Logs.error(f"clock_in_photo_save_failed_user_{user.id}", exc_info=e)
                    return {
                        "status": "error",
                        "message": "invalid_photo_data"
                    }

            AttendanceSession.objects.create(**attendance_data)

            Logs.atuta_logger(f"User clocked in | user={user.user_id} | {timestamp}")
            return {
                "status": "success",
                "message": "clock_in_recorded"
            }

        except Exception as e:
            Logs.error(f"clock_in_failed_user_{user.id}", exc_info=e)
            return {
                "status": "error",
                "message": "clock_in_failed"
            }


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
            Logs.error(f"clock_out_failed_user_{user.id}", exc_info=e)
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
            Logs.error(f"lunch_in_failed_user_{user.id}", exc_info=e)
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
            Logs.error(f"lunch_out_failed_user_{user.id}", exc_info=e)
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
