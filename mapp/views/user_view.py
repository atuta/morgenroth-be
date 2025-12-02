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

from mapp.classes.user_service import UserService
from mapp.classes.logs.logs import Logs

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
        if not email or not first_name or not last_name:
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
        Logs.error("api_add_user_failed", exc_info=e)
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
        Logs.error("api_change_password_failed", exc_info=e)
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
        Logs.error("api_login_failed", exc_info=e)
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