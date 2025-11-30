from typing import Optional
from mapp.models import SystemSettings
from mapp.classes.logs.logs import Logs


class SystemSettingService:

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
