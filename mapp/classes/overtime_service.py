from typing import Optional
from datetime import date as date_type
from django.db.models import Sum
from mapp.models import CustomUser, OvertimeAllowance
from mapp.classes.logs.logs import Logs


class OvertimeService:

    @classmethod
    def authorize_overtime(
        cls,
        user: CustomUser,
        date: date_type,
        hours: float,
        approved_by: Optional[CustomUser] = None
    ):
        """
        Authorize an overtime record for a user on a specific date.
        """
        try:
            ot = OvertimeAllowance.objects.create(
                user=user,
                date=date,
                hours=hours,
                approved_by=approved_by,
                approved_flag=True
            )
            Logs.atuta_logger(f"Overtime authorized for user {user.user_id} | hours={hours} | date={date}")
            return {
                "status": "success",
                "message": "overtime_authorized"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"authorize_overtime_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "overtime_authorization_failed"
            }

    @classmethod
    def get_user_overtime(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Fetch all authorized overtime for a user for the given month/year.
        Returns total hours and list of records.
        """
        try:
            qs = OvertimeAllowance.objects.filter(
                user=user,
                date__month=month,
                date__year=year,
                approved_flag=True
            )
            total_hours = qs.aggregate(Sum('hours'))['hours__sum'] or 0
            data = [
                {
                    "date": o.date,
                    "hours": o.hours,
                    "approved_by": o.approved_by.full_name if o.approved_by else None
                }
                for o in qs.order_by('-date')
            ]
            Logs.atuta_logger(f"Fetched overtime for user {user.user_id} | count={len(data)} | total_hours={total_hours}")
            return {
                "status": "success",
                "message": {
                    "total_hours": total_hours,
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_user_overtime_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "overtime_fetch_failed"
            }
