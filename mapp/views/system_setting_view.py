from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.system_setting_service import SystemSettingService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_system_setting(request):
    """
    Create or update a system setting.
    """
    try:
        key = request.data.get("key")
        value = request.data.get("value")
        description = request.data.get("description")

        if not key or not value:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        result = SystemSettingService.set_setting(
            key=key,
            value=value,
            description=description
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_set_system_setting_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_system_setting(request):
    """
    Fetch a system setting by key.
    """
    try:
        key = request.GET.get("key")

        if not key:
            return Response({"status": "error", "message": "missing_key"}, status=400)

        result = SystemSettingService.get_setting(key=key)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_system_setting_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
