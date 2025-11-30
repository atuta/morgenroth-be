import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.overtime_service import OvertimeService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_authorize_overtime(request):
    """
    Authorize overtime for a user.
    """
    try:
        date = request.data.get("date")
        hours = request.data.get("hours")

        if not date or hours is None:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            date = datetime.date.fromisoformat(date)
        except ValueError:
            return Response({"status": "error", "message": "invalid_date"}, status=400)

        try:
            hours = float(hours)
        except ValueError:
            return Response({"status": "error", "message": "invalid_hours"}, status=400)

        result = OvertimeService.authorize_overtime(
            user=request.user,
            date=date,
            hours=hours,
            approved_by=request.user  # if the current user is the approver
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_authorize_overtime_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_overtime(request):
    """
    Fetch overtime for a given month/year.
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

        result = OvertimeService.get_user_overtime(
            user=request.user,
            month=month,
            year=year
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_overtime_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
