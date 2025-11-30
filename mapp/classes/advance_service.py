from typing import Optional, List
from mapp.models import CustomUser, AdvancePayment
from mapp.classes.logs.logs import Logs
from django.db.models import Sum


class AdvanceService:

    @classmethod
    def create_advance(
        cls,
        user: CustomUser,
        amount: float,
        month: int,
        year: int,
        approved_by: Optional[CustomUser] = None
    ):
        """
        Create an advance payment record for a user.
        """
        try:
            advance = AdvancePayment.objects.create(
                user=user,
                amount=amount,
                month=month,
                year=year,
                approved_by=approved_by
            )
            Logs.atuta_logger(f"Advance created for user {user.user_id} | amount={amount} | {month}/{year}")
            return {
                "status": "success",
                "message": "advance_created"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"create_advance_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "advance_creation_failed"
            }

    @classmethod
    def get_user_advances(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Fetch all advances for a user for the given month/year.
        Returns total sum as well.
        """
        try:
            qs = AdvancePayment.objects.filter(user=user, month=month, year=year)
            total = qs.aggregate(Sum('amount'))['amount__sum'] or 0
            data = [
                {
                    "amount": a.amount,
                    "approved_by": a.approved_by.full_name if a.approved_by else None,
                    "month": a.month,
                    "year": a.year
                }
                for a in qs.order_by('-id')
            ]
            Logs.atuta_logger(f"Fetched advances for user {user.user_id} | count={len(data)} | total={total}")
            return {
                "status": "success",
                "message": {
                    "total": total,
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_user_advances_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "advance_fetch_failed"
            }
