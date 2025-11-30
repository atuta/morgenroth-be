from typing import Optional, List
from django.utils import timezone
from mapp.models import SupportTicket, CustomUser
from mapp.classes.logs.logs import Logs


class SupportTicketService:

    @classmethod
    def create_ticket(
        cls,
        user: CustomUser,
        subject: str,
        description: str
    ):
        """
        Create a support ticket for a user.
        """
        try:
            ticket = SupportTicket.objects.create(
                user=user,
                subject=subject,
                description=description,
                status="open",
                created_at=timezone.now()
            )
            Logs.atuta_logger(f"Support ticket created | user={user.user_id} | subject={subject}")
            return {
                "status": "success",
                "message": "support_ticket_created"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"create_support_ticket_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "support_ticket_creation_failed"
            }

    @classmethod
    def update_ticket(
        cls,
        ticket_id: int,
        status: str,
        resolved_at: Optional[timezone.datetime] = None
    ):
        """
        Update the status of a support ticket. Optionally set resolved_at.
        """
        try:
            ticket = SupportTicket.objects.filter(id=ticket_id).first()
            if not ticket:
                return {
                    "status": "error",
                    "message": "ticket_not_found"
                }
            ticket.status = status
            if resolved_at:
                ticket.resolved_at = resolved_at
            ticket.save()
            Logs.atuta_logger(f"Support ticket updated | id={ticket_id} | status={status}")
            return {
                "status": "success",
                "message": "support_ticket_updated"
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"update_support_ticket_failed_id_{ticket_id}", exc_info=e)
            return {
                "status": "error",
                "message": "support_ticket_update_failed"
            }

    @classmethod
    def get_user_tickets(
        cls,
        user: CustomUser
    ):
        """
        Fetch all support tickets for a specific user.
        """
        try:
            tickets = SupportTicket.objects.filter(user=user).order_by('-created_at')
            data = [
                {
                    "subject": t.subject,
                    "description": t.description,
                    "status": t.status,
                    "created_at": t.created_at,
                    "resolved_at": t.resolved_at
                } for t in tickets
            ]
            Logs.atuta_logger(f"Fetched support tickets | user={user.user_id} | count={len(data)}")
            return {
                "status": "success",
                "message": {
                    "records": data
                }
            }
        except Exception as e:
            Logs.atuta_technical_logger(f"get_user_support_tickets_failed_user_{user.user_id}", exc_info=e)
            return {
                "status": "error",
                "message": "support_ticket_fetch_failed"
            }
