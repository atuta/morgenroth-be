from datetime import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.models import CustomUser
from mapp.classes.support_ticket_service import SupportTicketService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_support_ticket(request):
    """
    Create a support ticket for the authenticated user.
    """
    try:
        subject = request.data.get("subject")
        description = request.data.get("description")

        if not subject or not description:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        result = SupportTicketService.create_ticket(
            user=request.user,
            subject=subject,
            description=description
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_create_support_ticket_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_support_ticket(request):
    """
    Update a support ticket's status. Optionally set resolved_at.
    """
    try:
        ticket_id = request.data.get("ticket_id")
        status = request.data.get("status")
        resolved_at = request.data.get("resolved_at")  # optional ISO datetime

        if not ticket_id or not status:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        resolved_dt = None
        if resolved_at:
            try:
                resolved_dt = datetime.fromisoformat(resolved_at)
            except ValueError:
                return Response({"status": "error", "message": "invalid_resolved_at"}, status=400)

        result = SupportTicketService.update_ticket(
            ticket_id=int(ticket_id),
            status=status,
            resolved_at=resolved_dt
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_update_support_ticket_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_tickets(request):
    """
    Fetch all support tickets for the authenticated user.
    """
    try:
        result = SupportTicketService.get_user_tickets(user=request.user)
        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_tickets_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
