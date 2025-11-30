from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mapp.classes.deduction_service import DeductionService
from mapp.classes.logs.logs import Logs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_deduction(request):
    """
    Create or update a statutory deduction.
    """
    try:
        name = request.data.get("name")
        percentage = request.data.get("percentage")

        if not name or percentage is None:
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        try:
            percentage = float(percentage)
        except ValueError:
            return Response({"status": "error", "message": "invalid_percentage"}, status=400)

        result = DeductionService.set_deduction(
            name=name,
            percentage=percentage
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_set_deduction_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_deduction(request):
    """
    Get a deduction by name.
    """
    try:
        name = request.GET.get("name")

        if not name:
            return Response({"status": "error", "message": "missing_name"}, status=400)

        result = DeductionService.get_deduction(name)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_deduction_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
