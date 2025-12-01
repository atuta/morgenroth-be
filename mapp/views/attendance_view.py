import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser, AttendanceSession
from mapp.classes.attendance_service import AttendanceService
from mapp.classes.logs.logs import Logs


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_current_session(request):
    """
    Retrieve the user's current active attendance session (clocked in but not clocked out).
    """
    try:
        result = AttendanceService.get_current_session(user=request.user)

        if result["status"] == "error":
            if result["message"] == "no_active_session":
                return Response(result, status=404)  # Not found
            return Response(result, status=400)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_current_session_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_clock_in(request):
    timestamp = request.data.get("timestamp")
    photo_base64 = request.data.get("photo_base64") or None

    if not timestamp:
        return Response(
            {"status": "error", "message": "missing_timestamp"},
            status=400
        )

    # Robust parsing that handles Z suffix and offsets
    try:
        timestamp = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return Response(
            {"status": "error", "message": "invalid_timestamp_format"},
            status=400
        )

    result = AttendanceService.clock_in(
        user=request.user,
        timestamp=timestamp,
        photo_base64=photo_base64
    )

    # proper HTTP status mapping
    if result["status"] == "success":
        return Response(result, status=201)

    if result["message"] == "active_session_exists":
        return Response(result, status=409)

    if result["message"] == "invalid_photo_data":
        return Response(result, status=422)

    if result["message"] == "missing_timestamp":
        return Response(result, status=400)

    # Everything else we treat as server failure
    return Response(result, status=500)

    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_clock_out(request):
    """
    Clock out a user.
    """
    try:
        timestamp = request.data.get("timestamp")
        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)
        from django.utils import timezone
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp)

        result = AttendanceService.clock_out(
            user=request.user,
            timestamp=timestamp
        )

        if result["status"] == "error":
            if result["message"] == "no_active_session":
                return Response(result, status=409)  # Conflict
            return Response(result, status=400)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_clock_out_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_lunch_in(request):
    """
    Record lunch in.
    """
    try:
        timestamp = request.data.get("timestamp")
        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)

        result = AttendanceService.lunch_in(
            user=request.user,
            timestamp=timestamp
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_lunch_in_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_lunch_out(request):
    """
    Record lunch out.
    """
    try:
        timestamp = request.data.get("timestamp")
        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)

        result = AttendanceService.lunch_out(
            user=request.user,
            timestamp=timestamp
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_lunch_out_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_total_hours(request):
    """
    Calculate total hours for the last active session.
    """
    try:
        session = AttendanceSession.objects.filter(user=request.user).last()

        if not session:
            return Response({"status": "error", "message": "no_session"}, status=404)

        result = AttendanceService.calculate_total_hours(session)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_total_hours_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
