from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.system_setting_service import SystemSettingService
from mapp.classes.logs.logs import Logs


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_working_hours(request):
    """
    Get all configured working hours for a given timezone.
    If no timezone is passed, default is Africa/Nairobi.
    """
    try:
        # Read timezone from query params if provided
        timezone = request.query_params.get("timezone", "Africa/Nairobi")

        result = SystemSettingService.get_working_hours(timezone=timezone)

        # If service reported an internal/business error
        if result.get("status") == "error":
            return Response(result, status=400)

        # Otherwise success
        return Response(result, status=200)

    except Exception as e:
        # Logs.atuta_technical_logger("api_get_working_hours_failed", exc_info=e)
        print(f"Server Error: {e}")
        return Response(
            {"status": "error", "message": "server_error"},
            status=500
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_working_hours(request):
    """
    Create or update working hours configuration for a specific day.
    """
    try:
        # Retrieve input data
        day_of_week = request.data.get("day_of_week")
        start_time = request.data.get("start_time")
        end_time = request.data.get("end_time")
        timezone = request.data.get("timezone", "Africa/Nairobi")  # default timezone

        # Validate required fields
        if not day_of_week or not start_time or not end_time:
            return Response(
                {"status": "error", "message": "missing_parameters"}, status=400
            )

        # Call service to save/update working hours
        result = SystemSettingService.set_working_hours(
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone
        )

        if result.get("status") == "error":
            return Response(result, status=400)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_set_working_hours_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_system_setting(request):
    """
    Create or update a system setting.
    """
    try:
        key = request.data.get("key")
        value = request.data.get("value")
        description = request.data.get("description")

        if not key or not value:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        result = SystemSettingService.set_setting(
            key=key,
            value=value,
            description=description
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_set_system_setting_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_system_setting(request):
    """
    Fetch a system setting by key.
    """
    try:
        key = request.GET.get("key")

        if not key:
            return Response({"status": "error", "message": "missing_key"}, status=400)

        result = SystemSettingService.get_setting(key=key)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_system_setting_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
