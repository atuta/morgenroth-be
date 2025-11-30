from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser
from mapp.classes.advance_service import AdvanceService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_advance(request):
    """
    Create an advance payment entry for a user.
    Expected JSON:
    {
        "user_id": "<uuid>",
        "amount": 1200,
        "month": 11,
        "year": 2025,
        "approved_by": "<uuid>" (optional)
    }
    """
    try:
        user_id = request.data.get("user_id")
        amount = request.data.get("amount")
        month = request.data.get("month")
        year = request.data.get("year")
        approved_by_id = request.data.get("approved_by")

        if not user_id or not amount or not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        # The user receiving the advance
        user = CustomUser.objects.get(user_id=user_id)

        approved_by = None
        if approved_by_id:
            approved_by = CustomUser.objects.get(user_id=approved_by_id)

        result = AdvanceService.create_advance(
            user=user,
            amount=amount,
            month=month,
            year=year,
            approved_by=approved_by
        )

        return Response(result, status=200 if result["status"] == "success" else 500)

    except CustomUser.DoesNotExist:
        return Response({"status": "error", "message": "user_not_found"}, status=404)

    except Exception as e:
        Logs.atuta_technical_logger("api_create_advance_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_advances(request):
    """
    Fetch all advances for a user for a given month and year.
    Query params:
    /api/advances?user_id=123&month=10&year=2024
    """
    try:
        user_id = request.query_params.get("user_id")
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not user_id or not month or not year:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        user = CustomUser.objects.get(user_id=user_id)

        result = AdvanceService.get_user_advances(
            user=user,
            month=month,
            year=year
        )

        return Response(result, status=200 if result["status"] == "success" else 500)

    except CustomUser.DoesNotExist:
        return Response({"status": "error", "message": "user_not_found"}, status=404)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_advances_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
