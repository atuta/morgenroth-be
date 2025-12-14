from datetime import datetime
from mapp.configs.working_hours import WorkingHours
from mapp.classes.logs.logs import Logs


class WorkingHoursService:
    """
    Service class for working hours management.
    All methods return:
        {
            "status": "success" | "fail",
            "message": any
        }
    """

    HOURS = WorkingHours.HOURS

    @classmethod
    def get_all_working_hours(cls):
        """
        Returns working hours for all roles.
        Intended for frontend presentation.
        """
        try:
            if not cls.HOURS:
                Logs.atuta_logger("No working hours configuration found")
                return {
                    "status": "success",
                    "message": {},
                }

            return {
                "status": "success",
                "message": cls.HOURS,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_all_working_hours_failed", exc_info=e)
            return {
                "status": "fail",
                "message": {},
            }


    @classmethod
    def get_hours(cls, role: str, day: str):
        """
        Returns start and end working hours for a given role and day.
        """
        try:
            role_hours = cls.HOURS.get(role.lower())
            if not role_hours:
                Logs.atuta_logger(f"No working hours configured for role: {role}")
                return {
                    "status": "success",
                    "message": None,
                }

            day_hours = role_hours.get(day.lower())
            if not day_hours:
                Logs.atuta_logger(f"No working hours configured for role={role}, day={day}")
                return {
                    "status": "success",
                    "message": None,
                }

            return {
                "status": "success",
                "message": day_hours,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_hours_failed", exc_info=e)
            return {
                "status": "fail",
                "message": None,
            }

    @classmethod
    def get_start_time(cls, role: str, day: str):
        """
        Returns start time for role and day.
        """
        try:
            result = cls.get_hours(role, day)
            if result["status"] != "success" or not result["message"]:
                return {
                    "status": "success",
                    "message": None,
                }

            return {
                "status": "success",
                "message": result["message"].get("start"),
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_start_time_failed role={role}, day={day}", exc_info=e
            )
            return {
                "status": "fail",
                "message": None,
            }

    @classmethod
    def get_end_time(cls, role: str, day: str):
        """
        Returns end time for role and day.
        """
        try:
            result = cls.get_hours(role, day)
            if result["status"] != "success" or not result["message"]:
                return {
                    "status": "success",
                    "message": None,
                }

            return {
                "status": "success",
                "message": result["message"].get("end"),
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_end_time_failed role={role}, day={day}", exc_info=e
            )
            return {
                "status": "fail",
                "message": None,
            }

    @classmethod
    def is_within_working_hours(cls, role: str, day: str, check_time: str):
        """
        Checks if a given time (HH:MM) is within working hours.
        """
        try:
            result = cls.get_hours(role, day)
            if result["status"] != "success" or not result["message"]:
                Logs.atuta_logger(
                    f"Working hours missing for validation role={role}, day={day}"
                )
                return {
                    "status": "success",
                    "message": False,
                }

            hours = result["message"]

            start = datetime.strptime(hours["start"], "%H:%M").time()
            end = datetime.strptime(hours["end"], "%H:%M").time()
            current = datetime.strptime(check_time, "%H:%M").time()

            return {
                "status": "success",
                "message": start <= current <= end,
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"is_within_working_hours_failed role={role}, day={day}, time={check_time}",
                exc_info=e,
            )
            return {
                "status": "fail",
                "message": False,
            }
