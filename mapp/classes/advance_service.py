from typing import Optional, List
from django.utils import timezone
from datetime import date
from mapp.models import CustomUser, AdvancePayment
from mapp.classes.logs.logs import Logs
from django.db.models import Sum


class AdvanceService:

    @classmethod
    def get_user_advances(cls, user_id, start_date=None, end_date=None):
        """
        Returns all advance payments for a specific user.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        """
        try:
            advances = AdvancePayment.objects.filter(user__user_id=user_id).select_related("approved_by")

            # Optional date filtering
            if start_date:
                advances = advances.filter(created_at__date__gte=start_date)
            if end_date:
                advances = advances.filter(created_at__date__lte=end_date)

            data = []

            for adv in advances:
                record = {
                    "advance_id": str(adv.advance_id),
                    "amount": adv.amount,
                    "month": adv.month,
                    "year": adv.year,
                    "approved_by": adv.approved_by.full_name if adv.approved_by else None,
                    "remarks": adv.remarks,
                    "created_at": adv.created_at,
                }
                data.append(record)

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_user_advances_failed", exc_info=e)
            return {
                "status": "error",
                "message": "user_advance_fetch_failed",
            }


    @classmethod
    def get_all_advances(cls, start_date=None, end_date=None):
        """
        Returns all advance payments.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        """
        try:
            advances = AdvancePayment.objects.select_related("user", "approved_by").all()

            # Apply optional date filtering
            if start_date:
                advances = advances.filter(created_at__date__gte=start_date)
            if end_date:
                advances = advances.filter(created_at__date__lte=end_date)

            data = []

            for adv in advances:
                record = {
                    "advance_id": str(adv.advance_id),
                    "user_id": str(adv.user.user_id),
                    "user_full_name": adv.user.full_name,
                    "user_email": adv.user.email,
                    "amount": adv.amount,
                    "month": adv.month,
                    "year": adv.year,
                    "approved_by": adv.approved_by.full_name if adv.approved_by else None,
                    "remarks": adv.remarks,
                    "created_at": adv.created_at,
                }
                data.append(record)

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_all_advances_failed", exc_info=e)
            return {
                "status": "error",
                "message": "advance_fetch_failed",
            }

    @classmethod
    def create_advance(
        cls,
        user: CustomUser,
        amount: float,
        remarks: str = "",
        approved_by: Optional[CustomUser] = None,
        month: Optional[int] = None,
        year: Optional[int] = None
    ):
        """
        Create an advance payment record for a user.
        Uses provided month/year or defaults to the current month/year.
        """
        try:
            now = timezone.now()
            month = month or now.month
            year = year or now.year

            advance = AdvancePayment.objects.create(
                user=user,
                amount=amount,
                remarks=remarks,
                approved_by=approved_by,
                month=month,
                year=year
            )

            Logs.atuta_logger(
                f"Advance created for user {user.user_id} | amount={amount} | month={month}/{year} | remarks={remarks}"
            )

            return {
                "status": "success",
                "message": "advance_created",
                "advance_id": str(advance.advance_id)
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"create_advance_failed_user_{user.user_id}", 
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_creation_failed"
            }


    @classmethod
    def get_user_advances_by_month(
        cls,
        user: CustomUser,
        start_date: date = None,
        end_date: date = None
    ):
        """
        Fetch user advances within a date range (based on created_at).
        If no date range is provided, return all records for the user.
        Returns total amount and advance records.
        """
        try:
            qs = AdvancePayment.objects.filter(user=user)

            # Apply range if provided
            if start_date:
                qs = qs.filter(created_at__date__gte=start_date)
            if end_date:
                qs = qs.filter(created_at__date__lte=end_date)

            total = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            data = [
                {
                    "amount": float(a.amount),
                    "remarks": a.remarks,
                    "approved_by": a.approved_by.full_name if a.approved_by else None,
                    "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for a in qs.order_by('-created_at')
            ]

            Logs.atuta_logger(
                f"Fetched advances for user {user.user_id} | count={len(data)} | total={total}"
            )

            return {
                "status": "success",
                "message": {
                    "total": total,
                    "records": data
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_user_advances_failed_user_{user.user_id}", 
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_fetch_failed"
            }
        
    @classmethod
    def get_all_user_advances(cls, user: CustomUser):
        """
        Fetch all advances for a user regardless of date.
        Returns total amount and list of advance records.
        """
        try:
            qs = AdvancePayment.objects.filter(user=user)
            total = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            data = [
                {
                    "amount": float(a.amount),
                    "remarks": a.remarks,
                    "approved_by": a.approved_by.full_name if a.approved_by else None,
                    "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for a in qs.order_by('-created_at')
            ]

            Logs.atuta_logger(
                f"Fetched all advances for user {user.user_id} | count={len(data)} | total={total}"
            )

            return {
                "status": "success",
                "message": {
                    "total": total,
                    "records": data
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_all_user_advances_failed_user_{user.user_id}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_fetch_failed"
            }

        
    

