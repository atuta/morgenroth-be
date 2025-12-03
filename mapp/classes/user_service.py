import datetime
from django.db.models import Max
from decimal import Decimal
from django.utils import timezone
from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from mapp.models import CustomUser, AttendanceSession
from mapp.classes.logs.logs import Logs


class UserService:

    @classmethod
    def get_user_details(cls, user_id):
        """
        Get complete user data using user_id.
        Returns user dict or error if not found.
        """
        try:
            user = CustomUser.objects.get(user_id=user_id)

            user_data = model_to_dict(user)
            
            # Handle image URL
            user_data["photo"] = user.photo.url if user.photo else None

            Logs.atuta_logger(f"Fetched details for user {user.email}")

            return {
                "status": "success",
                "data": user_data
            }

        except ObjectDoesNotExist:
            Logs.atuta_logger(f"User not found for ID {user_id}")
            return {
                "status": "error",
                "message": "user_not_found"
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_user_details_failed", exc_info=e)
            return {
                "status": "error",
                "message": "failed_to_fetch_user"
            }

    @classmethod
    def get_non_admin_users(cls):
        """
        Return a list of all users whose role is NOT 'admin'.
        Handles missing photo field safely.
        """
        # Removed 'user_id' from this list, as we will add it manually (and reliably) below
        FIELDS_TO_INCLUDE = [
            'first_name', 'last_name', 'email', 'account', 
            'user_role', 'phone_number', 'hourly_rate', 
            'hourly_rate_currency', 'status'
        ]
        
        try:
            users = CustomUser.objects.exclude(user_role="admin")
            user_list = []

            for user in users:
                # 1. Create the dictionary from non-PK fields
                user_dict = model_to_dict(user, fields=FIELDS_TO_INCLUDE)
                
                # 🚀 CRITICAL FIX: Manually and explicitly add the primary key (user_id)
                # This ensures the UUID field is correctly included regardless of model_to_dict quirks.
                user_dict["user_id"] = str(user.user_id) # Convert UUID to string for JSON serialization
                
                # 2. Safely handle photo field URL
                user_dict["photo"] = user.photo.url if user.photo else None
                
                # Log data fetched for debugging
                # Logs.atuta_logger(f"User data fetched: {user_dict}")
                
                user_list.append(user_dict)

            Logs.atuta_logger(f"Successfully fetched {len(user_list)} non-admin users")
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
