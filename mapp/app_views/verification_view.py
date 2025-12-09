import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.verification_service import VerificationService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_record_verification(request):
    try:
        status = request.data.get('status')
        photo = request.data.get('photo')
        reason = request.data.get('reason')

        if not status:
            return Response({"status": "error", "message": "missing_status"}, status=400)

        result = VerificationService.record_verification(
            user=request.user,
            status=status,
            photo=photo,
            reason=reason
        )
        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_record_verification_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_verification_history(request):
    """
    Fetch verification history for the authenticated user.
    Optional query parameters: start_date, end_date in ISO format.
    """
    try:
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        date_range = None
        if start_date and end_date:
            try:
                start_dt = datetime.datetime.fromisoformat(start_date)
                end_dt = datetime.datetime.fromisoformat(end_date)
                date_range = (start_dt, end_dt)
            except ValueError:
                return Response({"status": "error", "message": "invalid_date_format"}, status=400)

        result = VerificationService.get_verification_history(
            user=request.user,
            date_range=date_range
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_verification_history_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
