from typing import Optional, List, Tuple
from datetime import datetime
from mapp.models import CustomUser, SMSLog
from mapp.classes.logs.logs import Logs


class SMSService:

    @classmethod
    def send_sms(
        cls,
        recipient: CustomUser,
        message: str
    ):
        """
        Send an SMS to a recipient.
        Currently placeholder: just logs and stores in SMSLog.
        """
        try:
            # Placeholder: Integrate with actual SMS provider later
            log_entry = SMSLog.objects.create(
                recipient=recipient,
                message=message,
                status="sent",
                timestamp=datetime.now()
            )
            Logs.atuta_logger(f"SMS sent to user {recipient.user_id} | message={message}")
            return {
                "status": "success",
                "message": "sms_sent"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"sms_send_failed_user_{recipient.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "sms_send_failed"
            }

    @classmethod
    def get_sms_log(
        cls,
        user: Optional[CustomUser] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None
    ):
        """
        Fetch SMS log entries. Optionally filter by user and/or date range.
        """
        try:
            qs = SMSLog.objects.all()
            if user:
                qs = qs.filter(recipient=user)
            if date_range:
                start, end = date_range
                qs = qs.filter(timestamp__gte=start, timestamp__lte=end)

            data = [
                {
                    "recipient": sms.recipient.full_name,
                    "message": sms.message,
                    "status": sms.status,
                    "timestamp": sms.timestamp
                } for sms in qs.order_by('-timestamp')
            ]
            Logs.atuta_logger(f"Fetched SMS logs | count={len(data)}")
            return {
                "status": "success",
                "message": {
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger("get_sms_log_failed", exc_info=e)
            return {
                "status": "error",
                "message": "sms_log_fetch_failed"
            }
