from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.system_message_service import SystemMessageService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_system_message(request):
    """
    Create a system message for a user.
    """
    try:
        recipient_id = request.data.get("recipient_id")
        message = request.data.get("message")

        if not recipient_id or not message:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        from mapp.models import CustomUser
        try:
            recipient = CustomUser.objects.get(id=recipient_id)
        except CustomUser.DoesNotExist:
            return Response({"status": "error", "message": "recipient_not_found"}, status=404)

        result = SystemMessageService.create_message(
            recipient=recipient,
            message=message
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_create_system_message_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_mark_system_message_as_read(request):
    """
    Mark a system message as read.
    """
    try:
        message_id = request.data.get("message_id")

        if not message_id:
            return Response({"status": "error", "message": "missing_message_id"}, status=400)

        result = SystemMessageService.mark_as_read(message_id=int(message_id))

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_mark_system_message_as_read_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
