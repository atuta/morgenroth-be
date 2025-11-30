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