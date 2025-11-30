from typing import Optional, List
from django.utils import timezone
from mapp.models import AdminNotice, CustomUser
from mapp.classes.logs.logs import Logs


class AdminNoticeService:

    @classmethod
    def create_notice(
        cls,
        title: str,
        content: str,
        recipients: Optional[List[CustomUser]] = None,
        is_active: bool = True
    ):
        """
        Create an admin notice. Recipients can be all users or specific users.
        """
        try:
            notice = AdminNotice.objects.create(
                title=title,
                content=content,
                is_active=is_active,
                created_at=timezone.now()
            )
            if recipients:
                notice.recipients.set(recipients)
            notice.save()

            Logs.atuta_logger(f"Admin notice created | title={title} | recipients_count={len(recipients) if recipients else 'all'}")
            return {
                "status": "success",
                "message": "admin_notice_created"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"create_admin_notice_failed_title_{title}", exc_info=e)
            return {
                "status": "error",
                "message": "admin_notice_creation_failed"
            }

    @classmethod
    def get_notices(
        cls,
        user: Optional[CustomUser] = None
    ):
        """
        Fetch admin notices. If user is specified, fetch only those directed to user or all.
        """
        try:
            qs = AdminNotice.objects.filter(is_active=True)
            if user:
                qs = qs.filter(recipients__in=[user]) | qs.filter(recipients=None)
            data = [
                {
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "is_active": n.is_active,
                    "created_at": n.created_at
                } for n in qs.order_by('-created_at')
            ]
            Logs.atuta_logger(f"Fetched admin notices | count={len(data)}")
            return {
                "status": "success",
                "message": {
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger("get_admin_notices_failed", exc_info=e)
            return {
                "status": "error",
                "message": "admin_notices_fetch_failed"
            }

    @classmethod
    def update_notice(
        cls,
        notice_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        is_active: Optional[bool] = None
    ):
        """
        Update an existing admin notice.
        """
        try:
            notice = AdminNotice.objects.filter(id=notice_id).first()
            if not notice:
                return {
                    "status": "error",
                    "message": "notice_not_found"
                }

            if title is not None:
                notice.title = title
            if content is not None:
                notice.content = content
            if is_active is not None:
                notice.is_active = is_active

            notice.save()
            Logs.atuta_logger(f"Admin notice updated | id={notice_id}")
            return {
                "status": "success",
                "message": "admin_notice_updated"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"update_admin_notice_failed_id_{notice_id}", exc_info=e)
            return {
                "status": "error",
                "message": "admin_notice_update_failed"
            }

    @classmethod
    def delete_notice(cls, notice_id: int):
        """
        Delete an admin notice.
        """
        try:
            notice = AdminNotice.objects.filter(id=notice_id).first()
            if not notice:
                return {
                    "status": "error",
                    "message": "notice_not_found"
                }

            notice.delete()
            Logs.atuta_logger(f"Admin notice deleted | id={notice_id}")
            return {
                "status": "success",
                "message": "admin_notice_deleted"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"delete_admin_notice_failed_id_{notice_id}", exc_info=e)
            return {
                "status": "error",
                "message": "admin_notice_deletion_failed"
            }
