from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.user_manual_service import UserManualService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_user_manual(request):
    """
    Add a new user manual (file path or URL reference).
    """
    try:
        title = request.data.get("title")
        file_path = request.data.get("file_path")
        url = request.data.get("url")
        description = request.data.get("description")

        if not title:
            return Response({"status": "error", "message": "missing_title"}, status=400)

        result = UserManualService.add_manual(
            title=title,
            file_path=file_path,
            url=url,
            description=description
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_add_user_manual_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_manual(request):
    """
    Fetch user manuals. Optional filter by title.
    """
    try:
        title = request.GET.get("title")

        result = UserManualService.get_manual(title=title)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_manual_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
