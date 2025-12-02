import datetime
from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from mapp.models import CustomUser
from mapp.classes.logs.logs import Logs


class UserService:

    @classmethod
    def get_non_admin_users(cls):
        """
        Return a list of all users whose role is NOT 'admin'.
        Handles missing photo field safely.
        """
        try:
            users = CustomUser.objects.exclude(user_role="admin")
            user_list = []

            for user in users:
                user_dict = model_to_dict(user)
                # Safely handle photo field
                user_dict["photo"] = user.photo.url if user.photo else None
                user_list.append(user_dict)

            Logs.atuta_logger(f"Fetched {len(user_list)} non-admin users")
            return {
                "status": "success",
                "data": user_list
            }
        except Exception as e:
            Logs.atuta_technical_logger("get_non_admin_users_failed", exc_info=e)
            return {
                "status": "error",
                "message": "failed_to_fetch_users"
            }


    @classmethod
    def add_user(
        cls,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        user_role: str = "subordinate",
        phone_number: str = None,
        id_number: str = None,
        nssf_number: str = None,
        shif_sha_number: str = None,
        **extra_fields
    ):
        """
        Creates a new CustomUser with optional staff fields.
        """
        if not email or not first_name or not last_name or not password:
            return {
                "status": "error",
                "message": "missing_required_fields"
            }

        try:
            user = CustomUser.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                user_role=user_role,
                phone_number=phone_number,
                id_number=id_number,
                nssf_number=nssf_number,
                shif_sha_number=shif_sha_number,
                **extra_fields
            )

            return {
                "status": "success",
                "message": f"user_created_{user.user_id}",
                "user_id": user.user_id
            }

        except IntegrityError as e:
            Logs.atuta_technical_logger(f"user_creation_failed_{email}", exc_info=e)
            return {
                "status": "error",
                "message": "email_already_exists"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"user_creation_failed_{email}", exc_info=e)
            return {
                "status": "error",
                "message": "user_creation_failed"
            }



    @classmethod
    def change_password(cls, user: CustomUser, old_password: str, new_password: str):
        """
        Change the password for a user after validating the old password.
        """
        if not old_password or not new_password:
            return {
                "status": "error",
                "message": "both_old_and_new_password_required"
            }

        try:
            # Verify the old password first
            if not user.check_password(old_password):
                return {
                    "status": "error",
                    "message": "old_password_incorrect"
                }

            # Set and save the new password
            user.set_password(new_password)
            user.save()

            return {
                "status": "success",
                "message": "password_changed_successfully"
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"password_change_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "password_change_failed"
            }


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
