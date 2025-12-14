from typing import Optional
from decimal import Decimal
from django.db.models import Sum
from mapp.models import (
    CustomUser,
    AttendanceSession,
    StatutoryDeduction,
    AdvancePayment,
    OvertimeAllowance,
    HourCorrection
)
from mapp.classes.logs.logs import Logs
from django.utils import timezone
from django.core.paginator import Paginator
import os


class PayrollService:

    def get_hour_corrections(user_id=None, month=None, year=None, page=1, per_page=20):
        """
        Returns a paginated list of HourCorrection records.

        Optional filters:
            - user_id: filter by specific user
            - month: filter by month (1-12)
            - year: filter by year
        Pagination:
            - page: current page number (default 1)
            - per_page: number of records per page (default 20)
        """

        corrections = HourCorrection.objects.select_related('user').all()

        if user_id:
            corrections = corrections.filter(user__user_id=user_id)
        if month:
            corrections = corrections.filter(month=month)
        if year:
            corrections = corrections.filter(year=year)

        paginator = Paginator(corrections, per_page)
        page_obj = paginator.get_page(page)

        # Prepare serialized data
        results = []
        for correction in page_obj.object_list:
            user = correction.user
            results.append({
                "correction_id": str(correction.correction_id),
                "user_id": str(user.user_id),
                "full_name": user.full_name,
                "user_role": user.user_role,  # <-- added this line
                "photo": user.photo.url if user.photo else None,
                "hours": float(correction.hours),
                "hourly_rate": float(correction.hourly_rate),
                "amount": float(correction.amount),
                "reason": correction.reason,
                "date": correction.date.isoformat(),
                "month": correction.month,
                "year": correction.year,
                "corrected_by_id": str(correction.corrected_by.user_id) if correction.corrected_by else None,
                "created_at": correction.created_at.isoformat(),
            })

        return {
            "results": results,
            "total_records": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        }


    @classmethod
    def record_hour_correction(
        cls,
        user: CustomUser,
        hours: float,
        reason: str,
        corrected_by: Optional[CustomUser] = None,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ):
        """
        Record a manual hour correction for a user.
        Positive hours = add hours
        Negative hours = deduct hours
        """

        try:
            now = timezone.now()
            month = month or now.month
            year = year or now.year

            # Pull hourly_rate directly from user
            hourly_rate = user.hourly_rate

            correction = HourCorrection.objects.create(
                user=user,
                hours=hours,
                hourly_rate=hourly_rate,
                reason=reason,
                corrected_by=corrected_by,
                month=month,
                year=year,
                date=now.date(),
            )

            Logs.atuta_logger(
                f"Hour correction recorded for user {user.user_id} | "
                f"hours={hours} | "
                f"rate={correction.hourly_rate} | "
                f"amount={correction.amount} | "
                f"month={month}/{year} | "
                f"reason={reason}"
            )

            return {
                "status": "success",
                "message": "hour_correction_recorded",
                "correction_id": str(correction.correction_id),
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"hour_correction_record_failed_user_{user.user_id}",
                exc_info=e,
            )
            return {
                "status": "error",
                "message": "hour_correction_record_failed",
            }


    @classmethod
    def generate_detailed_payslip(cls, user: CustomUser, month: int, year: int):
        """
        Generate a detailed payslip for a user for a given month and year.
        Every section appears regardless of whether values exist.
        Includes:
        - Hourly rate
        - Attendance hours and daily pay
        - Overtime entries
        - Advance payments
        - Statutory deductions
        - Gross pay and net pay
        """
        try:
            # 1. Hourly rate
            rate_result = cls.get_hourly_rate(user)
            if rate_result["status"] != "success":
                raise Exception("Failed to fetch hourly rate")
            hourly_rate = rate_result["message"]["hourly_rate"]
            currency = rate_result["message"]["currency"]

            # 2. Attendance breakdown
            attendance_qs = AttendanceSession.objects.filter(
                user=user,
                date__month=month,
                date__year=year,
                status='closed'
            ).order_by('date')

            base_pay_breakdown = []
            total_hours = 0
            total_base_pay = 0

            if attendance_qs.exists():
                for session in attendance_qs:
                    hours = float(session.total_hours or 0)
                    pay = hours * hourly_rate
                    total_hours += hours
                    total_base_pay += pay
                    base_pay_breakdown.append({
                        "date": session.date.strftime("%Y-%m-%d"),
                        "hours": hours,
                        "pay": float(pay),
                        "notes": session.notes or ""
                    })
            else:
                # Always include at least one entry
                base_pay_breakdown.append({
                    "date": None,
                    "hours": 0.0,
                    "pay": 0.0,
                    "notes": ""
                })

            # 3. Overtime breakdown
            overtime_qs = OvertimeAllowance.objects.filter(
                user=user,
                month=month,
                year=year
            ).order_by('date')

            overtime_breakdown = []
            total_overtime = 0

            if overtime_qs.exists():
                for ot in overtime_qs:
                    amount = float(ot.amount or 0)
                    total_overtime += amount
                    overtime_breakdown.append({
                        "date": ot.date.strftime("%Y-%m-%d"),
                        "hours": float(ot.hours),
                        "amount": amount,
                        "remarks": ot.remarks or ""
                    })
            else:
                overtime_breakdown.append({
                    "date": None,
                    "hours": 0.0,
                    "amount": 0.0,
                    "remarks": ""
                })

            # 4. Gross pay
            gross_pay = total_base_pay + total_overtime

            # 5. Deductions breakdown
            deductions_result = cls.get_all_deductions()
            deductions_breakdown = []
            total_deductions = 0

            if deductions_result["status"] == "success":
                for d in deductions_result["message"]:
                    amount = gross_pay * (d["percentage"] / 100)
                    total_deductions += amount
                    deductions_breakdown.append({
                        "name": d["name"],
                        "percentage": d["percentage"],
                        "amount": float(amount)
                    })
            else:
                # Fallback: no deductions
                deductions_breakdown.append({
                    "name": "No Deductions",
                    "percentage": 0.0,
                    "amount": 0.0
                })

            # 6. Advance payments breakdown
            advance_qs = AdvancePayment.objects.filter(
                user=user,
                month=month,
                year=year
            ).order_by('created_at')

            advance_breakdown = []
            total_advance = 0

            if advance_qs.exists():
                for adv in advance_qs:
                    amount = float(adv.amount or 0)
                    total_advance += amount
                    advance_breakdown.append({
                        "date": adv.created_at.strftime("%Y-%m-%d"),
                        "amount": amount,
                        "remarks": adv.remarks or "",
                        "approved_by": adv.approved_by.full_name if adv.approved_by else None
                    })
            else:
                advance_breakdown.append({
                    "date": None,
                    "amount": 0.0,
                    "remarks": "",
                    "approved_by": None
                })

            # 7. Net pay
            net_pay = gross_pay - total_deductions - total_advance

            Logs.atuta_logger(
                f"Generated detailed payslip for user {user.user_id} | {month}/{year} | net_pay={net_pay} {currency}"
            )

            return {
                "status": "success",
                "message": {
                    "user": {
                        "id": str(user.user_id),
                        "full_name": user.full_name,
                        "email": user.email
                    },
                    "month": month,
                    "year": year,
                    "hourly_rate": float(hourly_rate),
                    "currency": currency,
                    "base_pay_breakdown": base_pay_breakdown,
                    "total_hours": float(total_hours),
                    "total_base_pay": float(total_base_pay),
                    "overtime_breakdown": overtime_breakdown,
                    "total_overtime": float(total_overtime),
                    "gross_pay": float(gross_pay),
                    "deductions_breakdown": deductions_breakdown,
                    "total_deductions": float(total_deductions),
                    "advance_breakdown": advance_breakdown,
                    "total_advance": float(total_advance),
                    "net_pay": float(net_pay)
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"generate_detailed_payslip_failed_user_{user.user_id}_{month}_{year}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "detailed_payslip_failed"
            }

    @classmethod
    def calculate_net_pay(cls, user: CustomUser, month: int, year: int):
        """
        Calculate net pay for a user for a given month and year.
        Breakdown includes: 
        - base pay from attendance hours
        - overtime amount
        - total statutory deductions
        - total advances
        - net pay
        """
        try:
            # 1. Get total hours and hourly rate
            hours_result = cls.get_total_hours_for_period(user, month, year)
            if hours_result["status"] != "success":
                raise Exception("Failed to fetch total hours")
            total_hours = hours_result["message"]["total_hours"]

            rate_result = cls.get_hourly_rate(user)
            if rate_result["status"] != "success":
                raise Exception("Failed to fetch hourly rate")
            hourly_rate = rate_result["message"]["hourly_rate"]
            currency = rate_result["message"]["currency"]

            base_pay = total_hours * hourly_rate

            # 2. Get total overtime
            ot_result = cls.get_total_overtime_amount_for_period(user, month, year)
            total_overtime = 0
            if ot_result["status"] == "success":
                total_overtime = ot_result["message"]["total_overtime_amount"]

            # 3. Calculate gross pay
            gross_pay = base_pay + total_overtime

            # 4. Get total statutory deductions
            deductions_result = cls.get_all_deductions()
            total_deductions = 0
            deductions_breakdown = []
            if deductions_result["status"] == "success":
                for d in deductions_result["message"]:
                    amount = gross_pay * (d["percentage"] / 100)
                    total_deductions += amount
                    deductions_breakdown.append({
                        "name": d["name"],
                        "percentage": d["percentage"],
                        "amount": float(amount)
                    })

            # 5. Get total advances
            advance_result = cls.get_total_advance_for_period(user, month, year)
            total_advance = 0
            if advance_result["status"] == "success":
                total_advance = advance_result["message"]["total_advance"]

            # 6. Calculate net pay
            net_pay = gross_pay - total_deductions - total_advance

            Logs.atuta_logger(
                f"Calculated net pay for user {user.user_id} | {month}/{year} | net_pay={net_pay} {currency}"
            )

            return {
                "status": "success",
                "message": {
                    "month": month,
                    "year": year,
                    "currency": currency,
                    "gross_pay": float(gross_pay),
                    "total_overtime": float(total_overtime),
                    "total_hours": float(total_hours),
                    "hourly_rate": float(hourly_rate),
                    "deductions_breakdown": deductions_breakdown,
                    "total_deductions": float(total_deductions),
                    "total_advance": float(total_advance),
                    "net_pay": float(net_pay)
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"calculate_net_pay_failed_user_{user.user_id}_{month}_{year}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "net_pay_calculation_failed"
            }

    @classmethod
    def get_hourly_rate(cls, user: CustomUser):
        """
        Fetch the hourly rate and currency for a user.
        """
        try:
            rate = float(user.hourly_rate or 0.0)
            currency = user.hourly_rate_currency or "KES"

            Logs.atuta_logger(
                f"Fetched hourly rate for user {user.user_id} | rate={rate} {currency}"
            )

            return {
                "status": "success",
                "message": {
                    "hourly_rate": rate,
                    "currency": currency
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_hourly_rate_failed_user_{user.user_id}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "hourly_rate_fetch_failed"
            }

    @classmethod
    def get_all_deductions(cls):
        """
        Fetch all statutory deductions.
        Returns a list of deductions with name and percentage.
        """
        try:
            qs = StatutoryDeduction.objects.all()

            data = [
                {
                    "name": d.name,
                    "percentage": float(d.percentage)
                }
                for d in qs
            ]

            Logs.atuta_logger(
                f"Fetched all statutory deductions | count={len(data)}"
            )

            return {
                "status": "success",
                "message": data
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                "get_all_deductions_failed",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "deductions_fetch_failed"
            }

    @classmethod
    def get_total_overtime_amount_for_period(cls, user: CustomUser, month: int, year: int):
        """
        Get total overtime amount allocated to a user for the given month & year.
        """
        try:
            qs = OvertimeAllowance.objects.filter(
                user=user,
                month=month,
                year=year
            )

            total_amount = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            Logs.atuta_logger(
                f"Fetched total overtime amount for user {user.user_id} | {month}/{year} | total={total_amount}"
            )

            return {
                "status": "success",
                "message": {
                    "month": month,
                    "year": year,
                    "total_overtime_amount": float(total_amount)
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_total_overtime_amount_failed_user_{user.user_id}_{month}_{year}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "overtime_fetch_failed"
            }

    @classmethod
    def get_total_advance_for_period(cls, user: CustomUser, month: int, year: int):
        """
        Return total advance payments for a user for a given month & year.
        """
        try:
            qs = AdvancePayment.objects.filter(
                user=user,
                month=month,
                year=year
            )

            total = qs.aggregate(Sum('amount'))['amount__sum'] or 0

            Logs.atuta_logger(
                f"Fetched total advance for user {user.user_id} | {month}/{year} | total={total}"
            )

            return {
                "status": "success",
                "message": {
                    "month": month,
                    "year": year,
                    "total_advance": float(total)
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_total_advance_for_period_failed_user_{user.user_id}_{month}_{year}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "advance_fetch_failed"
            }
   
    @classmethod
    def get_total_hours_for_period(cls, user: CustomUser, month: int, year: int):
        """
        Fetch total hours worked by a user for a specific month & year.
        """
        try:
            qs = AttendanceSession.objects.filter(
                user=user,
                date__month=month,
                date__year=year,
                status='closed'  # only count completed sessions
            )

            total_hours = qs.aggregate(Sum('total_hours'))['total_hours__sum'] or 0

            Logs.atuta_logger(
                f"Fetched total working hours for user {user.user_id} | {month}/{year} | total={total_hours}"
            )

            return {
                "status": "success",
                "message": {
                    "month": month,
                    "year": year,
                    "total_hours": float(total_hours)
                }
            }

        except Exception as e:
            Logs.atuta_technical_logger(
                f"get_total_hours_for_period_failed_user_{user.user_id}_{month}_{year}",
                exc_info=e
            )
            return {
                "status": "error",
                "message": "hours_fetch_failed"
            }