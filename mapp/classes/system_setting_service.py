from typing import Optional
from mapp.models import SystemSettings, WorkingHoursConfig
from mapp.classes.logs.logs import Logs


class SystemSettingService:

    @classmethod
    def get_working_hours(cls, timezone: Optional[str] = "Africa/Nairobi"):
        """
        Retrieve all configured working hours for a given timezone.
        """
        try:
            configs = WorkingHoursConfig.objects.filter(
                timezone=timezone,
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
                    "start_time": cfg.start_time.strftime("%H:%M"),
                    "end_time": cfg.end_time.strftime("%H:%M"),
                    "timezone": cfg.timezone,
                    "is_active": cfg.is_active,
                }
                for cfg in configs
            ]

            Logs.atuta_logger(f"Working hours retrieved | timezone={timezone}")

            return {
                "status": "success",
                "message": "working_hours_fetched",
                "data": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_working_hours_failed", exc_info=e)
            return {
                "status": "error",
                "message": "working_hours_failed",
            }



    @classmethod
    def set_working_hours(
        cls,
        day_of_week: str,       # e.g., 'Monday', 'Tuesday', ...
        start_time: str,        # 'HH:MM' 24-hour format
        end_time: str,          # 'HH:MM' 24-hour format
        timezone: Optional[str] = "Africa/Nairobi"
    ):
        """
        Create or update working hours configuration for a specific day.
        Overwrites existing record if it exists.
        """
        try:
            config, created = WorkingHoursConfig.objects.update_or_create(
                day_of_week=day_of_week,
                defaults={
                    "start_time": start_time,
                    "end_time": end_time,
                    "timezone": timezone,
                }
            )

            action = "created" if created else "updated"
            Logs.atuta_logger(f"Working hours {action} | day={day_of_week}, start={start_time}, end={end_time}, tz={timezone}")

            return {
                "status": "success",
                "message": f"working_hours_{action}"
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"set_working_hours_failed_{day_of_week}", exc_info=e)
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
