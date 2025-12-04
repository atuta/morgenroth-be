from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser
from mapp.classes.advance_service import AdvanceService
from mapp.classes.logs.logs import Logs


# ---------------------------
# Admin-only: Create advance for any user
# ---------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_admin_create_advance(request):
    """
    Admin: Create an advance for a specific user.
    Expected JSON:
    {
        "user_id": "<uuid>",
        "amount": 1200,
        "remarks": "optional notes",
        "month": 11,    # optional, defaults to current month
        "year": 2025    # optional, defaults to current year
    }
    """
    try:
        user_id = request.data.get("user_id")
        amount = request.data.get("amount")
        remarks = request.data.get("remarks", "")
        month = request.data.get("month")
        year = request.data.get("year")

        if not user_id or amount is None:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            amount = float(amount)
        except ValueError:
            return Response({"status": "error", "message": "invalid_amount"}, status=400)

        try:
            user = CustomUser.objects.get(user_id=user_id)
        except CustomUser.DoesNotExist:
            return Response({"status": "error", "message": "user_not_found"}, status=404)

        result = AdvanceService.create_advance(
            user=user,
            amount=amount,
            remarks=remarks,
            month=month,
            year=year,
            approved_by=request.user  # admin is the approver
        )

        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_admin_create_advance_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


# ---------------------------
# User-facing: Get advances by month/year
# ---------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_advances_by_month(request):
    """
    Fetch advances for logged-in user for a specific month/year.
    Query params: ?month=11&year=2025
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

        result = AdvanceService.get_user_advances(user=request.user, month=month, year=year)
        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_advances_by_month_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


# ---------------------------
# User-facing: Get all advances
# ---------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_all_user_advances(request):
    """
    Fetch all advances for the logged-in user.
    """
    try:
        result = AdvanceService.get_all_user_advances(user=request.user)
        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_all_user_advances_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


# ---------------------------
# Admin-facing: Get advances by month/year for any user
# ---------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_get_user_advances_by_month(request):
    """
    Admin: Fetch advances for a specific user by month/year.
    Query params: ?user_id=<uuid>&month=11&year=2025
    """
    try:
        user_id = request.GET.get("user_id")
        month = request.GET.get("month")
        year = request.GET.get("year")

        if not user_id or not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"status": "error", "message": "invalid_month_or_year"}, status=400)

        try:
            user = CustomUser.objects.get(user_id=user_id)
        except CustomUser.DoesNotExist:
            return Response({"status": "error", "message": "user_not_found"}, status=404)

        result = AdvanceService.get_user_advances(user=user, month=month, year=year)
        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_admin_get_user_advances_by_month_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


# ---------------------------
# Admin-facing: Get all advances for any user
# ---------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_get_all_user_advances(request):
    """
    Admin: Fetch all advances for a specific user.
    Query params: ?user_id=<uuid>
    """
    try:
        user_id = request.GET.get("user_id")
        if not user_id:
            return Response({"status": "error", "message": "missing_user_id"}, status=400)

        try:
            user = CustomUser.objects.get(user_id=user_id)
        except CustomUser.DoesNotExist:
            return Response({"status": "error", "message": "user_not_found"}, status=404)

        result = AdvanceService.get_all_user_advances(user=user)
        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_admin_get_all_user_advances_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
