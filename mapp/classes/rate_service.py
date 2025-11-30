from typing import Optional
from mapp.models import RateSetting
from mapp.classes.logs.logs import Logs


class RateService:

    @classmethod
    def set_rate(
        cls,
        user_role: str,
        hourly_rate: float,
        overtime_multiplier: float,
        advance_limit: float
    ):
        """
        Create or update rate settings for a user role.
        """
        try:
            rate, created = RateSetting.objects.update_or_create(
                user_role=user_role,
                defaults={
                    "hourly_rate": hourly_rate,
                    "overtime_multiplier": overtime_multiplier,
                    "advance_limit": advance_limit
                }
            )
            Logs.atuta_logger(f"Rate set for role {user_role} | hourly_rate={hourly_rate}, overtime_multiplier={overtime_multiplier}, advance_limit={advance_limit}")
            return {
                "status": "success",
                "message": "rate_set_successfully"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"set_rate_failed_role_{user_role}", exc_info=e)
            return {
                "status": "error",
                "message": "rate_setting_failed"
            }

    @classmethod
    def get_rate(
        cls,
        user_role: str
    ):
        """
        Fetch rate settings for a given user role.
        """
        try:
            rate = RateSetting.objects.filter(user_role=user_role).first()
            if not rate:
                return {
                    "status": "error",
                    "message": "rate_not_found"
                }

            Logs.atuta_logger(f"Rate fetched for role {user_role}")
            return {
                "status": "success",
                "message": {
                    "hourly_rate": rate.hourly_rate,
                    "overtime_multiplier": rate.overtime_multiplier,
                    "advance_limit": rate.advance_limit
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_rate_failed_role_{user_role}", exc_info=e)
            return {
                "status": "error",
                "message": "rate_fetch_failed"
            }
