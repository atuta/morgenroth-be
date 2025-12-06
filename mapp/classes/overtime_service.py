from typing import Optional
from django.utils import timezone
from django.db.models import Sum
from mapp.models import CustomUser, OvertimeAllowance
from mapp.classes.logs.logs import Logs


class OvertimeService:

    @classmethod
    def get_all_overtimes(cls, start_date=None, end_date=None):
        """
        Returns all overtime allowance records.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        """
        try:
            overtimes = OvertimeAllowance.objects.select_related("user", "approved_by").all()

            # Optional date filtering
            if start_date:
                overtimes = overtimes.filter(created_at__date__gte=start_date)
            if end_date:
                overtimes = overtimes.filter(created_at__date__lte=end_date)

            data = []

            for ot in overtimes:
                record = {
                    "overtime_id": str(ot.overtime_id),
                    "user_id": str(ot.user.user_id),
                    "user_full_name": ot.user.full_name,
                    "user_email": ot.user.email,
                    "date": ot.date,
                    "month": ot.month,
                    "year": ot.year,
                    "hours": ot.hours,
                    "amount": ot.amount,
                    "approved_by": ot.approved_by.full_name if ot.approved_by else None,
                    "remarks": ot.remarks,
                    "created_at": ot.created_at,
                }
                data.append(record)

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_all_overtimes_failed", exc_info=e)
            return {
                "status": "error",
                "message": "overtime_fetch_failed",
            }

    @classmethod
    def get_user_overtimes(cls, user_id, start_date=None, end_date=None):
        """
        Returns all overtime allowance records for a specific user.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        """
        try:
            overtimes = OvertimeAllowance.objects.filter(user__user_id=user_id).select_related("approved_by")

            # Optional date filtering
            if start_date:
                overtimes = overtimes.filter(created_at__date__gte=start_date)
            if end_date:
                overtimes = overtimes.filter(created_at__date__lte=end_date)

            data = []

            for ot in overtimes:
                record = {
                    "overtime_id": str(ot.overtime_id),
                    "date": ot.date,
                    "month": ot.month,
                    "year": ot.year,
                    "hours": ot.hours,
                    "amount": ot.amount,
                    "approved_by": ot.approved_by.full_name if ot.approved_by else None,
                    "remarks": ot.remarks,
                    "created_at": ot.created_at,
                }
                data.append(record)

            return {
                "status": "success",
                "message": data,
            }

        except Exception as e:
            Logs.atuta_technical_logger("get_user_overtimes_failed", exc_info=e)
            return {
                "status": "error",
                "message": "user_overtime_fetch_failed",
            }

    @classmethod
    def record_overtime(
        cls,
        user: CustomUser,
        hours: float,
        amount: float,
        remarks: str = "",
        approved_by: Optional[CustomUser] = None,
        month: Optional[int] = None,
        year: Optional[int] = None
    ):
        """
        Record overtime for a user.
        Uses provided month/year or defaults to current month/year.
        """
        try:
            now = timezone.now()
            month = month or now.month
            year = year or now.year

            ot = OvertimeAllowance.objects.create(
                user=user,
                hours=hours,
                amount=amount,
                remarks=remarks,
                approved_by=approved_by,
                month=month,
                year=year,
                date=now.date()
            )

            Logs.atuta_logger(
                f"Overtime recorded for user {user.user_id} | hours={hours} | amount={amount} | month={month}/{year} | remarks={remarks}"
            )

            return {
                "status": "success",
                "message": "overtime_recorded",
                "overtime_id": str(ot.overtime_id)
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"overtime_record_failed_user_{user.user_id}", exc_info=e
            )
            return {
                "status": "error",
                "message": "overtime_record_failed"
            }

    @classmethod
    def get_user_overtime_by_month(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Fetch all overtime records for a user for the given month/year.
        Returns total hours and amount, along with list of records.
        """
        try:
            qs = OvertimeAllowance.objects.filter(user=user, month=month, year=year)
            total_hours = qs.aggregate(Sum('hours'))['hours__sum'] or 0
            total_amount = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            data = [
                {
                    "hours": float(o.hours),
                    "amount": float(o.amount),
                    "remarks": o.remarks,
                    "approved_by": o.approved_by.full_name if o.approved_by else None,
                    "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for o in qs.order_by('-created_at')
            ]

            Logs.atuta_logger(
                f"Fetched overtime for user {user.user_id} | count={len(data)} | total_hours={total_hours} | total_amount={total_amount}"
            )

            return {
                "status": "success",
                "message": {
                    "total_hours": total_hours,
                    "total_amount": total_amount,
                    "records": data
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_user_overtime_failed_user_{user.user_id}", exc_info=e
            )
            return {
                "status": "error",
                "message": "overtime_fetch_failed"
            }

    @classmethod
    def get_all_user_overtime(cls, user: CustomUser):
        """
        Fetch all overtime records for a user, regardless of month/year.
        Returns total hours, total amount, and list of records.
        """
        try:
            qs = OvertimeAllowance.objects.filter(user=user)
            total_hours = qs.aggregate(Sum('hours'))['hours__sum'] or 0
            total_amount = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            data = [
                {
                    "hours": float(o.hours),
                    "amount": float(o.amount),
                    "remarks": o.remarks,
                    "approved_by": o.approved_by.full_name if o.approved_by else None,
                    "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for o in qs.order_by('-created_at')
            ]

            Logs.atuta_logger(
                f"Fetched all overtime for user {user.user_id} | count={len(data)} | total_hours={total_hours} | total_amount={total_amount}"
            )

            return {
                "status": "success",
                "message": {
                    "total_hours": total_hours,
                    "total_amount": total_amount,
                    "records": data
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_all_user_overtime_failed_user_{user.user_id}", exc_info=e
            )
            return {
                "status": "error",
                "message": "overtime_fetch_failed"
            }
