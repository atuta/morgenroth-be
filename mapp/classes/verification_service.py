from typing import Optional, Tuple
import base64
from django.core.files.base import ContentFile
from uuid import uuid4
from django.utils import timezone
from mapp.models import CustomUser, VerificationLog
from mapp.classes.logs.logs import Logs


class VerificationService:

    @classmethod
    def record_verification(cls, user, status, photo=None, reason=None):
        try:
            verification = VerificationLog(user=user, status=status.lower(), reason=reason)

            # Handle base64 photo
            if photo:
                format, imgstr = photo.split(';base64,')  # "data:image/jpeg;base64,..."
                ext = format.split('/')[-1]  # e.g., jpeg
                file_name = f"{uuid4()}.{ext}"
                verification.photo.save(file_name, ContentFile(base64.b64decode(imgstr)), save=False)

            verification.save()

            Logs.atuta_logger(f"Verification recorded for user {user.user_id} | status={status}")
            return {"status": "success", "message": "verification_recorded"}

        except Exception as e:
            Logs.atuta_technical_logger(f"record_verification_failed_user_{user.user_id}", exc_info=e)
            return {"status": "error", "message": "verification_recording_failed"}

    @classmethod
    def get_verification_history(
        cls,
        user: CustomUser,
        date_range: Optional[Tuple[timezone.datetime, timezone.datetime]] = None
    ):
        """
        Returns a list of verifications for the user.
        date_range: optional tuple (start_datetime, end_datetime)
        """
        try:
            qs = VerificationLog.objects.filter(user=user)
            if date_range:
                start, end = date_range
                qs = qs.filter(timestamp__gte=start, timestamp__lte=end)

            data = [
                {
                    "timestamp": v.timestamp,
                    "status": v.status,
                    "photo": v.photo.url if v.photo else None,
                    "reason": v.reason
                }
                for v in qs.order_by('-timestamp')
            ]

            Logs.atuta_logger(f"Fetched verification history for user {user.user_id} | count={len(data)}")
            return {
                "status": "success",
                "message": data
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"get_verification_history_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "verification_history_fetch_failed"
            }
