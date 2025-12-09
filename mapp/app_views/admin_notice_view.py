from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from mapp.models import CustomUser, AdminNotice
from mapp.classes.admin_notice_service import AdminNoticeService
from mapp.classes.logs.logs import Logs

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_admin_notice(request):
    """
    Create an admin notice.
    JSON payload example:
    {
        "title": "Notice Title",
        "content": "Notice content",
        "recipients": [user_id1, user_id2],  # Optional, leave empty for all
        "is_active": true
    }
    """
    try:
        title = request.data.get("title")
        content = request.data.get("content")
        recipients_ids = request.data.get("recipients", [])
        is_active = request.data.get("is_active", True)

        if not title or not content:
            return Response({"status": "error", "message": "title_or_content_missing"}, status=400)

        recipients = None
        if recipients_ids:
            recipients = CustomUser.objects.filter(user_id__in=recipients_ids)

        result = AdminNoticeService.create_notice(
            title=title,
            content=content,
            recipients=recipients,
            is_active=is_active
        )
        return Response(result, status=200 if result["status"] == "success" else 500)

    except Exception as e:
        Logs.atuta_technical_logger("api_create_admin_notice_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_admin_notices(request):
    """
    Fetch all active admin notices for the authenticated user.
    """
    try:
        user = request.user
        result = AdminNoticeService.get_notices(user=user)
        return Response(result, status=200 if result["status"] == "success" else 500)
    except Exception as e:
        Logs.atuta_technical_logger(f"api_get_admin_notices_failed_user_{request.user.user_id}", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_admin_notice(request):
    """
    Update an existing admin notice.
    JSON payload example:
    {
        "notice_id": "uuid",
        "title": "New Title",         # Optional
        "content": "New content",     # Optional
        "is_active": true             # Optional
    }
    """
    try:
        notice_id = request.data.get("notice_id")
        title = request.data.get("title")
        content = request.data.get("content")
        is_active = request.data.get("is_active")

        if not notice_id:
            return Response({"status": "error", "message": "notice_id_missing"}, status=400)

        result = AdminNoticeService.update_notice(
            notice_id=notice_id,
            title=title,
            content=content,
            is_active=is_active
        )
        return Response(result, status=200 if result["status"] == "success" else 400)

    except Exception as e:
        Logs.atuta_technical_logger("api_update_admin_notice_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_delete_admin_notice(request):
    """
    Delete an admin notice.
    JSON payload example:
    {
        "notice_id": "uuid"
    }
    """
    try:
        notice_id = request.data.get("notice_id")

        if not notice_id:
            return Response({"status": "error", "message": "notice_id_missing"}, status=400)

        result = AdminNoticeService.delete_notice(notice_id=notice_id)
        return Response(result, status=200 if result["status"] == "success" else 400)

    except Exception as e:
        Logs.atuta_technical_logger("api_delete_admin_notice_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
