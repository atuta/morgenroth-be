import datetime
from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors

from mapp.models import CustomUser
from mapp.classes.payroll_service import PayrollService
from mapp.classes.logs.logs import Logs


def admin_required(user):
    return user.user_role == 'admin'


def _generate_payslip_data(user, month: int, year: int):
    """
    Helper function to generate payslip data using PayrollService.
    """
    payslip_result = PayrollService.generate_detailed_payslip(user, month, year)
    if payslip_result["status"] != "success":
        return None
    data = payslip_result["message"]
    data["organization"] = "Morgenroth Schulhaus"
    return data


def _generate_payslip_pdf(user, data, month, year):
    """
    Helper function to create PDF in memory from payslip data.
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setTitle(f"Payslip_{user.full_name}_{month}_{year}")

    # HEADER
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(2*cm, height - 2*cm, data["organization"])
    pdf.setFont("Helvetica", 12)
    pdf.drawString(2*cm, height - 3*cm, f"Payslip for: {user.full_name} ({user.email})")
    pdf.drawString(2*cm, height - 4*cm, f"Month/Year: {month}/{year}")
    pdf.drawString(2*cm, height - 5*cm, f"Hourly Rate: {data['hourly_rate']} {data['currency']}")

    y = height - 6*cm

    # TABLE FUNCTION
    def draw_table(title, items, columns):
        nonlocal y
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(2*cm, y, title)
        y -= 0.5*cm
        pdf.setFont("Helvetica", 10)
        for item in items:
            row = " | ".join(f"{col}: {item.get(col, '-')}" for col in columns)
            pdf.drawString(2.2*cm, y, row)
            y -= 0.4*cm
        y -= 0.3*cm

    # ATTENDANCE
    draw_table("Attendance (Hours & Pay)", data["base_pay_breakdown"], ["date", "hours", "pay"])

    # OVERTIME
    draw_table("Overtime", data["overtime_breakdown"], ["date", "hours", "amount"])

    # ADVANCES
    draw_table("Advance Payments", data["advance_breakdown"], ["date", "amount", "approved_by"])

    # DEDUCTIONS
    draw_table("Statutory Deductions", data["deductions_breakdown"], ["name", "percentage", "amount"])

    # TOTALS
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(2*cm, y, "Totals")
    y -= 0.5*cm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(2.2*cm, y, f"Total Hours Worked: {data['total_hours']}")
    y -= 0.3*cm
    pdf.drawString(2.2*cm, y, f"Total Base Pay: {data['total_base_pay']} {data['currency']}")
    y -= 0.3*cm
    pdf.drawString(2.2*cm, y, f"Total Overtime: {data['total_overtime']} {data['currency']}")
    y -= 0.3*cm
    pdf.drawString(2.2*cm, y, f"Total Deductions: {data['total_deductions']} {data['currency']}")
    y -= 0.3*cm
    pdf.drawString(2.2*cm, y, f"Total Advances: {data['total_advance']} {data['currency']}")
    y -= 0.3*cm
    pdf.drawString(2.2*cm, y, f"Net Pay: {data['net_pay']} {data['currency']}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def _get_user_from_request(request, admin=False):
    """
    Helper to retrieve user either from request.user or query params for admin.
    """
    if admin:
        if not admin_required(request.user):
            return None, Response({"status": "error", "message": "Permission denied"}, status=403)
        user_id = request.GET.get("user_id")
        if not user_id:
            return None, Response({"status": "error", "message": "user_id query parameter is required"}, status=400)
        user = get_object_or_404(CustomUser, user_id=user_id)
        return user, None
    else:
        return request.user, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_user_payslip(request):
    """
    JSON payslip for the logged-in user.
    Admins can specify ?user_id=... to fetch any user's payslip.
    """
    today = datetime.date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    user, error_response = _get_user_from_request(request, admin=False)
    if error_response:
        return error_response

    try:
        data = _generate_payslip_data(user, month, year)
        if not data:
            return Response({"status": "error", "message": "Failed to generate payslip"}, status=400)

        return Response({"status": "success", "message": "Payslip generated successfully", "data": data})

    except Exception as e:
        Logs.atuta_technical_logger(
            f"generate_user_payslip_failed_user_{user.user_id}_{month}_{year}",
            exc_info=e
        )
        return Response({"status": "error", "message": "Payslip generation failed"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_user_payslip_pdf(request):
    """
    PDF payslip for the logged-in user.
    Admins can specify ?user_id=... to fetch any user's payslip.
    """
    today = datetime.date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    user, error_response = _get_user_from_request(request, admin=False)
    if error_response:
        return error_response

    try:
        data = _generate_payslip_data(user, month, year)
        if not data:
            return HttpResponse("Failed to generate payslip", status=400)

        buffer = _generate_payslip_pdf(user, data, month, year)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Payslip_{user.full_name}_{month}_{year}.pdf"'
        return response

    except Exception as e:
        Logs.atuta_technical_logger(
            f"generate_user_payslip_pdf_failed_user_{user.user_id}_{month}_{year}",
            exc_info=e
        )
        return HttpResponse("Payslip generation failed", status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_generate_user_payslip(request):
    """
    Admin-facing JSON payslip endpoint.
    """
    today = datetime.date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    user, error_response = _get_user_from_request(request, admin=True)
    if error_response:
        return error_response

    try:
        data = _generate_payslip_data(user, month, year)
        if not data:
            return Response({"status": "error", "message": "Failed to generate payslip"}, status=400)

        return Response({"status": "success", "message": "Payslip generated successfully", "data": data})

    except Exception as e:
        Logs.atuta_technical_logger(
            f"admin_generate_user_payslip_failed_user_{user.user_id}_{month}_{year}",
            exc_info=e
        )
        return Response({"status": "error", "message": "Payslip generation failed"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_generate_user_payslip_pdf(request):
    """
    Admin-facing PDF payslip endpoint.
    """
    today = datetime.date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    user, error_response = _get_user_from_request(request, admin=True)
    if error_response:
        return error_response

    try:
        data = _generate_payslip_data(user, month, year)
        if not data:
            return HttpResponse("Failed to generate payslip", status=400)

        buffer = _generate_payslip_pdf(user, data, month, year)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Payslip_{user.full_name}_{month}_{year}.pdf"'
        return response

    except Exception as e:
        Logs.atuta_technical_logger(
            f"admin_generate_user_payslip_pdf_failed_user_{user.user_id}_{month}_{year}",
            exc_info=e
        )
        return HttpResponse("Payslip generation failed", status=500)
