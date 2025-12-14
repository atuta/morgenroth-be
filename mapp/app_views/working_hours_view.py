from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.working_hours_service import WorkingHoursService
from mapp.classes.logs.logs import Logs


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_all_working_hours(request):
    """
    Fetch working hours for all user roles.
    Intended for frontend presentation.
    """
    try:
        result = WorkingHoursService.get_all_working_hours()

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_all_working_hours_failed", exc_info=e)
        return Response(
            {"status": "fail", "message": "server_error"},
            status=500
        )
