from typing import Optional
from mapp.models import SystemSettings, WorkingHoursConfig
from mapp.classes.logs.logs import Logs


class SystemSettingService:

    @classmethod
    def get_working_hours(
        cls,
        user_role: str,
        timezone: Optional[str] = "Africa/Nairobi"
    ):
        """
        Retrieve configured working hours for a given user role and timezone.
        """
        try:
            configs = WorkingHoursConfig.objects.filter(
                user_role=user_role,
                timezone=timezone,
                is_active=True,
            ).order_by('day_of_week')

            if not configs.exists():
                return {
                    "status": "success",
                    "message": "no_working_hours_found",
                    "data": []
                }

            data = [
                {
                    "day_of_week": cfg.day_of_week,
                    "day_name": cfg.get_day_of_week_display(),
                    "user_role": cfg.user_role,
                    "user_role_display": cfg.get_user_role_display(),
                    "start_time": cfg.start_time.strftime("%H:%M"),
                    "end_time": cfg.end_time.strftime("%H:%M"),
                    "timezone": cfg.timezone,
                    "is_active": cfg.is_active,
                }
                for cfg in configs
            ]

            Logs.atuta_logger(
                f"Working hours retrieved | role={user_role}, tz={timezone}"
            )

            return {
                "status": "success",
                "message": "working_hours_fetched",
                "data": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_working_hours_failed_role_{user_role}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "working_hours_failed",
            }


    @classmethod
    def set_working_hours(
        cls,
        day_of_week: int,          # 1–7 (use WorkingHoursConfig.Days)
        user_role: str,            # 'admin', 'office', 'teaching', etc.
        start_time: str,           # 'HH:MM'
        end_time: str,             # 'HH:MM'
        timezone: Optional[str] = "Africa/Nairobi"
    ):
        """
        Create or update working hours configuration for a specific day + role.
        Overwrites existing record if it exists.
        """
        try:
            config, created = WorkingHoursConfig.objects.update_or_create(
                day_of_week=day_of_week,
                user_role=user_role,
                timezone=timezone,
                defaults={
                    "start_time": start_time,
                    "end_time": end_time,
                    "is_active": True,
                }
            )

            action = "created" if created else "updated"

            Logs.atuta_logger(
                f"Working hours {action} | "
                f"day={day_of_week}, role={user_role}, "
                f"start={start_time}, end={end_time}, tz={timezone}"
            )

            return {
                "status": "success",
                "message": f"working_hours_{action}"
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"set_working_hours_failed_day_{day_of_week}_role_{user_role}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "working_hours_failed"
            }



    @classmethod
    def set_setting(
        cls,
        key: str,
        value: str,
        description: Optional[str] = None
    ):
        """
        Create or update a system setting.
        """
        try:
            setting, created = SystemSettings.objects.update_or_create(
                key=key,
                defaults={
                    "value": value,
                    "description": description
                }
            )
            Logs.atuta_logger(f"System setting set | key={key}, value={value}")
            return {
                "status": "success",
                "message": "system_setting_set"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"set_system_setting_failed_{key}", exc_info=e)
            return {
                "status": "error",
                "message": "system_setting_failed"
            }

    @classmethod
    def get_setting(
        cls,
        key: str
    ):
        """
        Fetch a system setting by key.
        """
        try:
            setting = SystemSettings.objects.filter(key=key).first()
            if not setting:
                return {
                    "status": "error",
                    "message": "setting_not_found"
                }
            Logs.atuta_logger(f"System setting fetched | key={key}")
            return {
                "status": "success",
                "message": {
                    "key": setting.key,
                    "value": setting.value,
                    "description": setting.description
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_system_setting_failed_{key}", exc_info=e)
            return {
                "status": "error",
                "message": "system_setting_fetch_failed"
            }
