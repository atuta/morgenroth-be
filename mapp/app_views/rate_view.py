from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.rate_service import RateService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_rate(request):
    """
    Set hourly rate and related fields for a role.
    """
    try:
        user_role = request.data.get("user_role")
        hourly_rate = request.data.get("hourly_rate")
        overtime_multiplier = request.data.get("overtime_multiplier")
        advance_limit = request.data.get("advance_limit")

        if not all([user_role, hourly_rate, overtime_multiplier, advance_limit]):
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            hourly_rate = float(hourly_rate)
            overtime_multiplier = float(overtime_multiplier)
            advance_limit = float(advance_limit)
        except ValueError:
            return Response({"status": "error", "message": "invalid_rate_values"}, status=400)

        result = RateService.set_rate(
            user_role=user_role,
            hourly_rate=hourly_rate,
            overtime_multiplier=overtime_multiplier,
            advance_limit=advance_limit
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_set_rate_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_rate(request):
    """
    Get rate settings for a role.
    """
    try:
        user_role = request.GET.get("user_role")

        if not user_role:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        result = RateService.get_rate(user_role=user_role)

        if result["status"] == "error":
            return Response(result, status=404)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_rate_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
