import datetime

import json
from rest_framework.decorators import api_view, permission_classes
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from mapp.serializers import UserPhotoSerializer

from mapp.classes.user_service import UserService
from mapp.classes.logs.logs import Logs

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_dashboard_metrics(request):
    """
    Returns combined metrics for the admin dashboard:
    - Attendance statistics
    - Monthly payroll metrics (salary, advance, net due)
    Accepts optional 'month' and 'year' as URL query parameters; defaults to current month/year.
    Example: /api/admin-dashboard-metrics/?month=12&year=2025
    """
    try:
        month = request.GET.get("month")
        year = request.GET.get("year")

        # Convert to int if provided
        if month is not None:
            try:
                month = int(month)
            except ValueError:
                return Response({"status": "error", "message": "invalid_month"}, status=400)

        if year is not None:
            try:
                year = int(year)
            except ValueError:
                return Response({"status": "error", "message": "invalid_year"}, status=400)

        result = UserService.admin_dashboard_metrics(month=month, year=year)
        return Response(result, status=200)

    except Exception as e:
        return Response({"status": "error", "message": "admin_dashboard_metrics_failed"}, status=500)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_user_holiday_status(request):
    """
    Admin updates a specific user's holiday status.
    Only a valid is_on_holiday value will be updated.
    """
    try:
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"status": "error", "message": "user_id_required"}, status=400)

        is_on_holiday = request.data.get("is_on_holiday")

        # Use the dedicated class method
        result = UserService.update_user_holiday_status(
            user_id=user_id,
            is_on_holiday=is_on_holiday
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("Holiday status update failed", exc_info=e)
        return Response({"status": "error", "message": "update_failed"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_user_leave_status(request):
    """
    Admin updates a specific user's leave status.
    Only a valid is_on_leave value will be updated.
    """
    try:
        # Get user_id from request data
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"status": "error", "message": "user_id_required"}, status=400)

        is_on_leave = request.data.get("is_on_leave")

        result = UserService.update_user_leave_status(
            user_id=user_id,
            is_on_leave=is_on_leave
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger(f"Holiday status update failed: ", exc_info=e)
        return Response({"status": "error", "message": "update_failed"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_user_photo(request):
    """
    Upload or update the logged-in user's profile photo.
    """
    user = request.user
    serializer = UserPhotoSerializer(user, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response({
            "status": "success",
            "message": "Photo uploaded successfully",
            "data": {"photo": serializer.data.get("photo")}
        })
    else:
        return Response({
            "status": "error",
            "message": "Invalid image",
            "errors": serializer.errors
        }, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_user_fields(request):
    """
    Admin updates a specific user's fields.
    Only fields provided in the request will be updated.
    Lunch start and end must be provided together.
    """
    try:
        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"status": "error", "message": "user_id_required"},
                status=400
            )

        nssf = request.data.get("nssf")
        sha = request.data.get("sha")
        hourly_rate = request.data.get("hourly_rate")
        lunch_start = request.data.get("lunch_start")
        lunch_end = request.data.get("lunch_end")

        result = UserService.update_user_fields(
            user_id=user_id,
            nssf=nssf,
            sha=sha,
            hourly_rate=hourly_rate,
            lunch_start=lunch_start,
            lunch_end=lunch_end,
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        return Response(
            {"status": "error", "message": "update_failed"},
            status=500
        )

    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_logged_in_user_details(request):
    """
    Get user details for the currently authenticated user
    """
    try:
        user_id = request.user.user_id  # UUID from CustomUser model

        result = UserService.get_user_details(user_id)
        status_code = 200 if result.get("status") == "success" else 400

        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_logged_in_user_details_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_details(request):
    """
    Get user details using query param ?user_id=<uuid>
    """
    try:
        user_id = request.GET.get("user_id")

        if not user_id:
            return Response({"status": "error", "message": "missing_user_id"}, status=400)

        result = UserService.get_user_details(user_id)
        status_code = 200 if result.get("status") == "success" else 400

        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_details_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_non_admin_users(request):
    """
    Fetch all users whose role is not 'admin'.
    """
    try:
        result = UserService.get_non_admin_users()

        # Return 200 for success, 400 if something went wrong
        status_code = 200 if result.get("status") == "success" else 400

        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_non_admin_users_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_user(request):
    """
    Create a new user (staff/admin/etc.)
    """
    try:
        data = request.data
        email = data.get("email")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        role = data.get("role", "subordinate")
        password = data.get("password", "changeme123")

        phone_number = data.get("phone_number")
        id_number = data.get("id_number")
        nssf_number = data.get("nssf_number")
        shif_sha_number = data.get("shif_sha_number")

        # Basic validation
        if not phone_number or not first_name or not last_name:
            return Response(
                {"status": "error", "message": "missing_required_fields"},
                status=400
            )

        result = UserService.add_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            user_role=role,
            password=password,
            phone_number=phone_number,
            id_number=id_number,
            nssf_number=nssf_number,
            shif_sha_number=shif_sha_number
        )

        return Response(result, status=200 if result["status"] == "success" else 400)

    except Exception as e:
        Logs.atuta_technical_logger("api_add_user_failed", exc_info=e)
        return Response(
            {"status": "error", "message": "server_error"},
            status=500
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_change_password(request):
    """
    Change password for authenticated user
    Requires old_password and new_password in the request body
    """
    try:
        data = request.data
        old_password = data.get("old_password")
        new_password = data.get("new_password")

        if not old_password or not new_password:
            return Response({"status": "error", "message": "missing_old_or_new_password"}, status=400)

        result = UserService.change_password(
            user=request.user,
            old_password=old_password,
            new_password=new_password
        )

        return Response(result, status=200 if result["status"] == "success" else 400)

    except Exception as e:
        Logs.atuta_technical_logger("api_change_password_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """
    Authenticate a user and return JWT access and refresh tokens.
    """
    try:
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response({"status": "error", "message": "missing_credentials"}, status=400)

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"status": "error", "message": "invalid_credentials"}, status=401)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        Logs.atuta_logger(f"User logged in | user_id={user.user_id}")

        return Response({
            "status": "success",
            "message": "login_successful",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user_id": user.user_id,
                "user_role": user.user_role,
                "full_name": UserService.full_name(user)["message"]["full_name"]
            }
        }, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_login_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_top_up_subscription(request):
    """
    Extend the authenticated user's subscription by a number of days.
    """
    try:
        days = request.data.get("days")
        if days is None:
            return Response({"status": "error", "message": "missing_days"}, status=400)

        try:
            days = int(days)
        except ValueError:
            return Response({"status": "error", "message": "invalid_days"}, status=400)

        result = UserService.top_up_subscription(user=request.user, days=days)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_top_up_subscription_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_full_name(request):
    """
    Fetch the full name of the authenticated user.
    """
    try:
        result = UserService.full_name(user=request.user)
        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_full_name_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_has_permission(request):
    """
    Check if the authenticated user has a specific permission.
    """
    try:
        perm = request.GET.get("perm")
        if not perm:
            return Response({"status": "error", "message": "missing_permission"}, status=400)

        result = UserService.has_permission(user=request.user, perm=perm)
        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_has_permission_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_has_module_permission(request):
    """
    Check if the authenticated user has access to a module.
    """
    try:
        module = request.GET.get("module")
        if not module:
            return Response({"status": "error", "message": "missing_module"}, status=400)

        result = UserService.has_module_permission(user=request.user, module=module)
        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_has_module_permission_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)

@csrf_exempt
def blank(request):
    try:
        # if request.method != 'POST':
        #     return JsonResponse({"status": "fail", "data": {"message": "Only POST requests are allowed!"}}, status=405)

        resp = {"status": "error", "message": "this is an api zone. silence is golden"}
        return JsonResponse(resp, content_type='application/json', safe=False)

    except json.JSONDecodeError:
        # Handle JSON decoding errors
        return JsonResponse({"status": "fail", "message": "Invalid JSON"}, status=400)

    except Exception as e:
        # Handle any other exceptions
        return JsonResponse({"status": "fail", "message": "error"}, status=500)