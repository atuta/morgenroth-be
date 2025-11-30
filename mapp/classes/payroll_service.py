from typing import Optional
from django.db.models import Sum
from mapp.models import (
    CustomUser,
    SalaryRecord,
    AdvancePayment,
    OvertimeAllowance,
    SalarySlip,
    PaymentReport
)
from mapp.classes.logs.logs import Logs
from django.utils import timezone
import os


class PayrollService:

    @classmethod
    def generate_monthly_salary(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Generate or update salary record for a user for the given month/year.
        """
        try:
            base_hours = user.attendancesession_set.filter(
                date__month=month, date__year=year
            ).aggregate(total=Sum('total_hours'))['total'] or 0

            overtime_hours = OvertimeAllowance.objects.filter(
                user=user, date__month=month, date__year=year, approved_flag=True
            ).aggregate(total=Sum('hours'))['total'] or 0

            advances = AdvancePayment.objects.filter(
                user=user, month=month, year=year
            ).aggregate(total=Sum('amount'))['total'] or 0

            # Fetch rates
            rate = user.ratesetting.hourly_rate if hasattr(user, 'ratesetting') else 0
            overtime_rate = rate * (user.ratesetting.overtime_multiplier if hasattr(user, 'ratesetting') else 1)

            base_pay = base_hours * rate
            overtime_pay = overtime_hours * overtime_rate
            net_pay = base_pay + overtime_pay - advances

            salary, created = SalaryRecord.objects.update_or_create(
                user=user, month=month, year=year,
                defaults={
                    'base_hours': base_hours,
                    'base_pay': base_pay,
                    'overtime_hours': overtime_hours,
                    'overtime_pay': overtime_pay,
                    'advances_deducted': advances,
                    'net_pay': net_pay
                }
            )
            Logs.atuta_logger(f"Salary generated for user {user.user_id} | {month}/{year}")
            return {
                "status": "success",
                "message": "salary_generated"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"generate_monthly_salary_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "salary_generation_failed"
            }

    @classmethod
    def calculate_net_salary(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Fetch the net salary for a user for given month/year.
        """
        try:
            salary = SalaryRecord.objects.filter(user=user, month=month, year=year).first()
            if not salary:
                return {
                    "status": "error",
                    "message": "salary_record_not_found"
                }
            Logs.atuta_logger(f"Net salary fetched for user {user.user_id} | {month}/{year}")
            return {
                "status": "success",
                "message": {
                    "net_pay": salary.net_pay,
                    "base_pay": salary.base_pay,
                    "overtime_pay": salary.overtime_pay,
                    "advances_deducted": salary.advances_deducted
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"calculate_net_salary_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "net_salary_calc_failed"
            }

    @classmethod
    def generate_salary_slip(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Generate a PDF salary slip for the user.
        Placeholder: just create record with dummy path for now.
        """
        try:
            slip_file_path = f"salary_slips/{user.account}_{year}_{month}.pdf"
            SalarySlip.objects.update_or_create(
                user=user, generated_at=timezone.now(),
                defaults={"file_path": slip_file_path}
            )
            Logs.atuta_logger(f"Salary slip generated for user {user.user_id} | {month}/{year}")
            return {
                "status": "success",
                "message": "salary_slip_generated"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"generate_salary_slip_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "salary_slip_generation_failed"
            }

    @classmethod
    def get_salary_slip(
        cls,
        user: CustomUser,
        month: int,
        year: int
    ):
        """
        Fetch salary slip record for the user for a given month/year.
        """
        try:
            slip = SalarySlip.objects.filter(user=user, generated_at__year=year, generated_at__month=month).first()
            if not slip:
                return {
                    "status": "error",
                    "message": "salary_slip_not_found"
                }
            Logs.atuta_logger(f"Salary slip fetched for user {user.user_id} | {month}/{year}")
            return {
                "status": "success",
                "message": {
                    "file_path": slip.file_path,
                    "generated_at": slip.generated_at
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_salary_slip_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "salary_slip_fetch_failed"
            }

    @classmethod
    def generate_payment_report(
        cls,
        month: int,
        year: int
    ):
        """
        Generate payment report for all users for the month/year.
        """
        try:
            salaries = SalaryRecord.objects.filter(month=month, year=year)
            total_paid = salaries.aggregate(Sum('net_pay'))['net_pay__sum'] or 0
            total_advances = salaries.aggregate(Sum('advances_deducted'))['advances_deducted__sum'] or 0
            balances = total_paid - total_advances
            report_file = f"payment_reports/{year}_{month}.pdf"

            PaymentReport.objects.update_or_create(
                month=month, year=year,
                defaults={
                    "total_paid": total_paid,
                    "total_advances": total_advances,
                    "balances": balances,
                    "file_path": report_file
                }
            )
            Logs.atuta_logger(f"Payment report generated | {month}/{year}")
            return {
                "status": "success",
                "message": "payment_report_generated"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"generate_payment_report_failed_{month}_{year}", exc_info=e)
            return {
                "status": "error",
                "message": "payment_report_generation_failed"
            }

    @classmethod
    def get_payment_summary(
        cls,
        month: int,
        year: int
    ):
        """
        Fetch payment report summary for the given month/year.
        """
        try:
            report = PaymentReport.objects.filter(month=month, year=year).first()
            if not report:
                return {
                    "status": "error",
                    "message": "payment_report_not_found"
                }
            Logs.atuta_logger(f"Payment report fetched | {month}/{year}")
            return {
                "status": "success",
                "message": {
                    "total_paid": report.total_paid,
                    "total_advances": report.total_advances,
                    "balances": report.balances,
                    "file_path": report.file_path
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_payment_summary_failed_{month}_{year}", exc_info=e)
            return {
                "status": "error",
                "message": "payment_summary_fetch_failed"
            }
