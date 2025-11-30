from typing import Optional
from mapp.models import SystemMessage, CustomUser
from mapp.classes.logs.logs import Logs
from django.utils import timezone


class SystemMessageService:

    @classmethod
    def create_message(
        cls,
        recipient: CustomUser,
        message: str
    ):
        """
        Create a system message for a user.
        """
        try:
            msg = SystemMessage.objects.create(
                recipient=recipient,
                message=message,
                created_at=timezone.now(),
                read_flag=False
            )
            Logs.atuta_logger(f"System message created for user {recipient.user_id}")
            return {
                "status": "success",
                "message": "system_message_created"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"create_system_message_failed_user_{recipient.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "system_message_creation_failed"
            }

    @classmethod
    def mark_as_read(
        cls,
        message_id: int
    ):
        """
        Mark a system message as read.
        """
        try:
            msg = SystemMessage.objects.filter(id=message_id).first()
            if not msg:
                return {
                    "status": "error",
                    "message": "system_message_not_found"
                }
            msg.read_flag = True
            msg.save()
            Logs.atuta_logger(f"System message marked as read | id={message_id}")
            return {
                "status": "success",
                "message": "system_message_marked_as_read"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"mark_system_message_as_read_failed_id_{message_id}", exc_info=e)
            return {
                "status": "error",
                "message": "system_message_mark_read_failed"
            }
