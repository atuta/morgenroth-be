from typing import Optional, List
from mapp.models import UserManual
from mapp.classes.logs.logs import Logs
from django.utils import timezone


class UserManualService:

    @classmethod
    def add_manual(
        cls,
        title: str,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        description: Optional[str] = None
    ):
        """
        Add a new user manual. Can be a file upload or URL reference.
        """
        try:
            manual = UserManual.objects.create(
                title=title,
                file_path=file_path,
                url=url,
                description=description
            )
            Logs.atuta_logger(f"User manual added | title={title}")
            return {
                "status": "success",
                "message": "user_manual_added"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"add_user_manual_failed_title_{title}", exc_info=e)
            return {
                "status": "error",
                "message": "user_manual_add_failed"
            }

    @classmethod
    def get_manual(
        cls,
        title: Optional[str] = None
    ):
        """
        Fetch user manuals. Can filter by title.
        """
        try:
            qs = UserManual.objects.all()
            if title:
                qs = qs.filter(title__icontains=title)

            data = [
                {
                    "title": m.title,
                    "file_path": m.file_path,
                    "url": m.url,
                    "description": m.description
                } for m in qs.order_by('-title')
            ]
            Logs.atuta_logger(f"Fetched user manuals | count={len(data)}")
            return {
                "status": "success",
                "message": {
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger("get_user_manual_failed", exc_info=e)
            return {
                "status": "error",
                "message": "user_manual_fetch_failed"
            }
