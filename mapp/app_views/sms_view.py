from datetime import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser
from mapp.classes.sms_service import SMSService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_send_sms(request):
    """
    Send an SMS to a user.
    """
    try:
        recipient_id = request.data.get("recipient_id")
        message = request.data.get("message")

        if not recipient_id or not message:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            recipient = CustomUser.objects.get(user_id=recipient_id)
        except CustomUser.DoesNotExist:
            return Response({"status": "error", "message": "recipient_not_found"}, status=404)

        result = SMSService.send_sms(
            recipient=recipient,
            message=message
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_send_sms_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_sms_log(request):
    """
    Fetch SMS log entries. Optional filters: user_id, start_date, end_date (ISO format).
    """
    try:
        user_id = request.GET.get("user_id")
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        user = None
        date_range = None

        if user_id:
            try:
                user = CustomUser.objects.get(user_id=user_id)
            except CustomUser.DoesNotExist:
                return Response({"status": "error", "message": "user_not_found"}, status=404)

        if start_date and end_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
                end_dt = datetime.fromisoformat(end_date)
                date_range = (start_dt, end_dt)
            except ValueError:
                return Response({"status": "error", "message": "invalid_date_format"}, status=400)

        result = SMSService.get_sms_log(
            user=user,
            date_range=date_range
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_sms_log_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
