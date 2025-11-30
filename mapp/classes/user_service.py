import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from mapp.models import CustomUser
from mapp.classes.logs.logs import Logs


class UserService:

    @classmethod
    def top_up_subscription(cls, user: CustomUser, days: int):
        if not isinstance(days, int) or days <= 0:
            return {
                "status": "error",
                "message": "invalid_days_param"
            }

        try:
            if user.subscription_expires is None:
                user.subscription_expires = datetime.date.today() + datetime.timedelta(days=days)
            else:
                user.subscription_expires = user.subscription_expires + datetime.timedelta(days=days)

            user.save()

            return {
                "status": "success",
                "message": "subscription_extended"
            }

        except Exception as e:
            Logs.error(f"subscription_top_up_failed_user_{user.id}", exc_info=e)
            return {
                "status": "error",
                "message": "subscription_update_failed"
            }


    @classmethod
    def full_name(cls, user: CustomUser):
        first = user.first_name or ""
        last = user.last_name or ""
        name = f"{first} {last}".strip() or user.username

        return {
            "status": "success",
            "message": {
                "full_name": name
            }
        }


    @classmethod
    def has_permission(cls, user: CustomUser, perm: str):
        if not perm:
            return {
                "status": "error",
                "message": "invalid_permission_param"
            }

        try:
            allowed = user.has_perm(perm)
            return {
                "status": "success",
                "message": {
                    "allowed": allowed,
                    "permission": perm
                }
            }
        except Exception as e:
            Logs.error(f"permission_check_failed_user_{user.id}", exc_info=e)
            return {
                "status": "error",
                "message": "permission_check_failed"
            }


    @classmethod
    def has_module_permission(cls, user: CustomUser, module: str):
        if not module:
            return {
                "status": "error",
                "message": "invalid_module_param"
            }

        try:
            allowed = user.has_module_perms(module)
            return {
                "status": "success",
                "message": {
                    "allowed": allowed,
                    "module": module
                }
            }

        except Exception as e:
            Logs.error(f"module_permission_check_failed_user_{user.id}", exc_info=e)
            return {
                "status": "error",
                "message": "module_permission_check_failed"
            }
