from typing import Optional, List
from django.utils import timezone
from datetime import date, datetime
from django.db.models import Q
from django.core.paginator import Paginator
from mapp.models import CustomUser, AdvancePayment
from mapp.classes.logs.logs import Logs
from django.db.models import Sum


class AdvanceService:

    @classmethod
    def update_advance(cls, advance_id, remarks=None, day=None, month=None, year=None):
        """
        Updates an advance record.
        Only fields provided will be updated.
        """
        try:
            advance = AdvancePayment.objects.select_related("user").get(advance_id=advance_id)

            updated_fields = []

            if remarks is not None:
                advance.remarks = remarks
                updated_fields.append("remarks")

            if day is not None:
                advance.day = int(day)
                updated_fields.append("day")

            if month is not None:
                advance.month = int(month)
                updated_fields.append("month")

            if year is not None:
                advance.year = int(year)
                updated_fields.append("year")

            if updated_fields:
                advance.save(update_fields=updated_fields)

            Logs.atuta_logger(
                f"Advance updated | advance_id={advance_id} | fields={','.join(updated_fields)}"
            )

            return {
                "status": "success",
                "message": "advance_updated",
                "advance_id": str(advance.advance_id)
            }

        except AdvancePayment.DoesNotExist:
            return {
                "status": "error",
                "message": "advance_not_found"
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"update_advance_failed_{advance_id}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_update_failed"
            }

    @classmethod
    def get_advance_by_id(cls, advance_id):
        """
        Returns a single advance payment record by advance_id.
        """
        try:
            advance = AdvancePayment.objects.select_related(
                "user", "approved_by"
            ).get(advance_id=advance_id)

            record = {
                "advance_id": str(advance.advance_id),

                "user_id": str(advance.user.user_id),
                "user_full_name": advance.user.full_name,
                "user_email": advance.user.email,

                "amount": float(advance.amount),

                "day": advance.day,
                "month": advance.month,
                "year": advance.year,

                "approved_by_id": str(advance.approved_by.user_id) if advance.approved_by else None,
                "approved_by": advance.approved_by.full_name if advance.approved_by else None,

                "remarks": advance.remarks,

                "created_at": advance.created_at.isoformat() if advance.created_at else None,
            }

            Logs.atuta_logger(
                f"Advance fetched | advance_id={advance_id} | user={advance.user.user_id}"
            )

            return {
                "status": "success",
                "message": record,
            }

        except AdvancePayment.DoesNotExist:
            return {
                "status": "error",
                "message": "advance_not_found",
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_advance_by_id_failed_{advance_id}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_fetch_failed",
            }

    @classmethod
    def get_user_advances(cls, user_id, start_date=None, end_date=None):
        """
        Returns all advance payments for a specific user.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        """
        try:
            advances = AdvancePayment.objects.filter(
                user__user_id=user_id
            ).select_related("approved_by")

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
                    "day": adv.day,  # added
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
    def get_all_advances(cls, start_date=None, end_date=None, page=1, per_page=20):
        """
        Returns paginated advance payments.
        Filters by the stored advance date fields: day, month, year.
        Optional filters:
            start_date: YYYY-MM-DD string or date object
            end_date: YYYY-MM-DD string or date object
        Pagination:
            page: current page number (default 1)
            per_page: number of records per page (default 20)
        """
        try:
            advances = AdvancePayment.objects.select_related("user", "approved_by").all()

            # Parse incoming string dates if needed
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Filter using stored advance date fields (year, month, day)
            if start_date:
                advances = advances.filter(
                    Q(year__gt=start_date.year) |
                    Q(year=start_date.year, month__gt=start_date.month) |
                    Q(year=start_date.year, month=start_date.month, day__gte=start_date.day)
                )

            if end_date:
                advances = advances.filter(
                    Q(year__lt=end_date.year) |
                    Q(year=end_date.year, month__lt=end_date.month) |
                    Q(year=end_date.year, month=end_date.month, day__lte=end_date.day)
                )

            # Order by actual stored advance date
            advances = advances.order_by("-year", "-month", "-day", "-created_at")

            paginator = Paginator(advances, per_page)
            page_obj = paginator.get_page(page)

            data = []

            for adv in page_obj.object_list:
                record = {
                    "advance_id": str(adv.advance_id),
                    "user_id": str(adv.user.user_id),
                    "user_full_name": adv.user.full_name,
                    "user_email": adv.user.email,
                    "amount": float(adv.amount),
                    "day": adv.day,
                    "month": adv.month,
                    "year": adv.year,
                    "approved_by": adv.approved_by.full_name if adv.approved_by else None,
                    "remarks": adv.remarks,
                    "created_at": adv.created_at.isoformat() if adv.created_at else None,
                }
                data.append(record)

            return {
                "status": "success",
                "message": {
                    "results": data,
                    "total_records": paginator.count,
                    "total_pages": paginator.num_pages,
                    "current_page": page_obj.number,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                },
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
        day: Optional[int] = None,
        month: Optional[int] = None,
        year: Optional[int] = None
    ):
        """
        Create an advance payment record for a user.
        Uses provided day/month/year or defaults to the current date.
        """
        try:
            now = timezone.now()
            day = day or now.day
            month = month or now.month
            year = year or now.year

            advance = AdvancePayment.objects.create(
                user=user,
                amount=amount,
                remarks=remarks,
                approved_by=approved_by,
                day=day,
                month=month,
                year=year
            )

            Logs.atuta_logger(
                f"Advance created for user {user.user_id} | amount={amount} | date={day}/{month}/{year} | remarks={remarks}"
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

                    # NEW FIELDS
                    "day": a.day,
                    "month": a.month,
                    "year": a.year,

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

        
    

