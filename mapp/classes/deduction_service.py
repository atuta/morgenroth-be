from typing import Optional
from mapp.models import StatutoryDeduction
from mapp.classes.logs.logs import Logs


class DeductionService:

    @classmethod
    def set_deduction(cls, name: str, percentage: float):
        """
        Create or update a statutory deduction.
        Overwrites existing record if it exists.
        """
        try:
            deduction, created = StatutoryDeduction.objects.update_or_create(
                name=name,
                defaults={"percentage": percentage}
            )

            action = "created" if created else "updated"
            Logs.atuta_logger(
                f"Deduction {action} | name={name}, percentage={percentage}"
            )

            return {
                "status": "success",
                "message": f"deduction_{action}"
            }

        except Exception as e:
            Logs.atuta_technical_logger(f"set_deduction_failed_{name}", exc_info=e)
            return {
                "status": "error",
                "message": "deduction_setting_failed"
            }


    @classmethod
    def get_deduction(cls, name: str):
        """
        Fetch a statutory deduction by name.
        """
        try:
            deduction = StatutoryDeduction.objects.get(name=name)
            Logs.atuta_logger(f"Deduction fetched | name={name}")
            return {
                "status": "success",
                "message": "deduction_fetched",
                "data": {
                    "name": deduction.name,
                    "percentage": float(deduction.percentage)
                }
            }
        except StatutoryDeduction.DoesNotExist:
            return {
                "status": "error",
                "message": "deduction_not_found",
                "data": None
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_deduction_failed_{name}", exc_info=e)
            return {
                "status": "error",
                "message": "deduction_fetch_failed",
                "data": None
            }
