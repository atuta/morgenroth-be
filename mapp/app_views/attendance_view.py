import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser, AttendanceSession
from mapp.classes.attendance_service import AttendanceService
from mapp.classes.logs.logs import Logs

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_attendance_history(request):
    """
    Retrieves attendance records based on date range and optional user filtering.
    QueryParams: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), user_id (optional)
    """
    try:
        # 1. Extract Query Parameters
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        requested_user_id = request.query_params.get("user_id")

        # 2. Permission Logic (RBAC)
        # If the user is NOT an admin/super, they are locked to their own ID
        if request.user.user_role not in ['super', 'admin']:
            target_user_id = str(request.user.user_id)
        else:
            # Admins can filter by a specific user or pass None for all users
            target_user_id = requested_user_id

        # 3. Date Parsing & Validation
        start_date = None
        end_date = None

        try:
            if start_date_str:
                start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if end_date_str:
                end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({
                "status": "error", 
                "message": "invalid_date_format_use_YYYY-MM-DD"
            }, status=400)

        # 4. Call the Service Layer
        result = AttendanceService.get_attendance_history(
            start_date=start_date,
            end_date=end_date,
            user_id=target_user_id
        )

        # 5. Response Mapping
        if result["status"] == "success":
            return Response(result, status=200)
        
        return Response(result, status=400)

    except Exception as e:
        # Technical log for server-side issues
        Logs.atuta_technical_logger(f"api_attendance_history_view_failed", exc_info=e)
        return Response({
            "status": "error",
            "message": "internal_server_error"
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_get_user_attendance_history(request):
    """
    Admin/staff fetches attendance records for any user.
    user_id must be supplied in request.data or query string.
    Optional filters: start_date, end_date
    """
    try:
        # Accept user_id either way — flexible
        user_id = request.data.get("user_id") or request.GET.get("user_id")

        if not user_id:
            return Response(
                {"status": "error", "message": "user_id_required"},
                status=400
            )

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        result = AttendanceService.get_user_attendance_history(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_admin_get_user_attendance_history_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_attendance_history(request):
    """
    Authenticated user fetches their own attendance history.
    Optional filters: start_date, end_date
    """
    try:
        start_date = request.GET.get("start_date")  # optional
        end_date = request.GET.get("end_date")      # optional

        user_id = request.user.user_id  # Force logged-in user only

        result = AttendanceService.get_user_attendance_history(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_attendance_history_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_today_user_time_summary(request):
    """
    Fetch today's attendance summary for all users with attendance activity.
    Includes earliest clock-in, latest clock-out, total hours worked,
    user photo URL, clock-in photo URL, and user role.
    """
    try:
        result = AttendanceService.get_today_user_time_summary()

        # Return 200 for success, 400 if something went wrong
        status_code = 200 if result.get("status") == "success" else 400

        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_today_user_time_summary_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
    

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
    """
    API endpoint for user clock-in. 
    Accepts timestamp, photo_base64, and clockin_type.
    """
    timestamp_str = request.data.get("timestamp")
    photo_base64 = request.data.get("photo_base64") or None
    # Default to "regular" if not provided by the frontend
    clockin_type = request.data.get("clockin_type", "regular") 

    if not timestamp_str:
        return Response(
            {"status": "error", "message": "missing_timestamp"},
            status=400
        )

    # Robust parsing that handles Z suffix and offsets
    try:
        # Using fromisoformat to match modern Python standards
        timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return Response(
            {"status": "error", "message": "invalid_timestamp_format"},
            status=400
        )

    # Call the updated service method
    result = AttendanceService.clock_in(
        user=request.user,
        timestamp=timestamp,
        clockin_type=clockin_type,
        photo_base64=photo_base64
    )

    # Proper HTTP status mapping
    if result["status"] == "success":
        return Response(result, status=201)

    # Logic-based errors
    if result["message"] == "active_session_exists":
        return Response(result, status=409)  # Conflict

    if result["message"] == "user_on_leave":
        return Response(result, status=403)  # Forbidden

    # Validation errors
    if result["message"] in ["invalid_photo_data", "invalid_clockin_type"]:
        return Response(result, status=422)  # Unprocessable Entity

    if result["message"] == "missing_timestamp":
        return Response(result, status=400)  # Bad Request

    # Everything else we treat as server failure
    return Response(result, status=500)

    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_clock_out(request):
    """
    Clock out a user with optional notes.
    Expected payload:
    {
        "timestamp": "2025-12-02T17:00:00",
        "notes": "Leaving early today"  # optional
    }
    """
    try:
        timestamp = request.data.get("timestamp")
        notes = request.data.get("notes")  # optional

        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)
        from django.utils import timezone
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp)

        result = AttendanceService.clock_out(
            user=request.user,
            timestamp=timestamp,
            notes=notes
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
