import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.payroll_service import PayrollService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_generate_monthly_salary(request):
    """
    Generate salary for a user.
    """
    try:
        month = request.data.get("month")
        year = request.data.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.generate_monthly_salary(
            user=request.user,
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_generate_monthly_salary_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_calculate_net_salary(request):
    """
    Calculate net salary for a user.
    """
    try:
        month = request.GET.get("month")
        year = request.GET.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.calculate_net_salary(
            user=request.user,
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_calculate_net_salary_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_generate_salary_slip(request):
    """
    Generate a salary slip.
    """
    try:
        month = request.data.get("month")
        year = request.data.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.generate_salary_slip(
            user=request.user,
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_generate_salary_slip_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_salary_slip(request):
    """
    Fetch salary slip.
    """
    try:
        month = request.GET.get("month")
        year = request.GET.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.get_salary_slip(
            user=request.user,
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_salary_slip_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_generate_payment_report(request):
    """
    Generate payment report for all users.
    """
    try:
        month = request.data.get("month")
        year = request.data.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.generate_payment_report(
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_generate_payment_report_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_payment_summary(request):
    """
    Get payment summary.
    """
    try:
        month = request.GET.get("month")
        year = request.GET.get("year")

        if not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        result = PayrollService.get_payment_summary(
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_payment_summary_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
