import datetime
from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, serializers, permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

# Reportlab Imports for PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib import colors
from reportlab.lib.units import cm

# Application Specific Imports
from mapp.models import CustomUser, OrganizationDetail
from mapp.classes.payroll_service import PayrollService
from mapp.classes.logs.logs import Logs

# --- PERMISSIONS & SERIALIZERS ---

class IsAdminUser(permissions.BasePermission):
    """Checks if the user has the 'admin' role in the custom user model."""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            getattr(request.user, 'user_role', None) == 'admin'
        )

class BatchPayslipSerializer(serializers.Serializer):
    """Validates the multi-user/multi-date payload."""
    user_ids = serializers.ListField(child=serializers.CharField(), required=True)
    start_month = serializers.IntegerField(min_value=1, max_value=12)
    start_year = serializers.IntegerField(min_value=2000)
    end_month = serializers.IntegerField(min_value=1, max_value=12)
    end_year = serializers.IntegerField(min_value=2000)

# --- PDF GENERATION ENGINE ---

def _draw_payslip_page(story, user, data, org, styles):
    """
    Single payslip page. Logo + org details + title all flush-left.
    Org details appear immediately below the logo.
    """
    page_width = A4[0] - 3*cm

    # --- Styles ---
    bold_style = ParagraphStyle('BoldNormal', fontName='Helvetica-Bold', fontSize=10, leftIndent=0, firstLineIndent=0)
    normal_style = ParagraphStyle('NormalFlush', fontName='Helvetica', fontSize=10, leftIndent=0, firstLineIndent=0)
    title_style = ParagraphStyle('TitleFlush', fontName='Helvetica-Bold', fontSize=14, leftIndent=0, firstLineIndent=0)
    contact_style = ParagraphStyle('ContactFlush', fontName='Helvetica', fontSize=9, leftIndent=0, firstLineIndent=0)

    # --- Header Table (Logo + Org details + Title) ---
    logo_cell = Spacer(1, 0)  # fallback spacer
    if org and getattr(org, "logo", None):
        try:
            logo_img = Image(org.logo.path, width=2.2*cm, height=2.2*cm)
            logo_img.hAlign = 'LEFT'
            logo_cell = logo_img
        except:
            logo_cell = Spacer(1, 2.2*cm)

    # Org details + title stacked vertically
    right_content = []
    org_name = (org.name if org else "MORGENROTH").upper()
    right_content.append(Paragraph(org_name, bold_style))
    if org:
        if getattr(org, "physical_address", None):
            right_content.append(Paragraph(f"Address: {org.physical_address}", contact_style))
        contact_parts = []
        for attr, label in [("postal_address", "P.O. Box"), ("telephone", "Tel"), ("email", "Email")]:
            val = getattr(org, attr, None)
            if val:
                contact_parts.append(f"{label}: {val}")
        if contact_parts:
            right_content.append(Paragraph(" | ".join(contact_parts), contact_style))
    # Title
    right_content.append(Spacer(1, 0.1*cm))
    right_content.append(Paragraph("OFFICIAL PAYSLIP", title_style))

    header_table = Table([[logo_cell, right_content]], colWidths=[2.5*cm, page_width - 2.5*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),  # org details directly below logo
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*cm))

    # --- Employee Info ---
    emp_data = [
        [Paragraph(f"<b>Employee:</b> {user.full_name}", normal_style),
         Paragraph(f"<b>Period:</b> {data['month']}/{data['year']}", normal_style)],
        [Paragraph(f"<b>Email:</b> {user.email}", normal_style),
         Paragraph(f"<b>Rate:</b> {data['hourly_rate']} {data['currency']}/hr", normal_style)]
    ]
    emp_table = Table(emp_data, colWidths=[page_width*0.65, page_width*0.35])
    emp_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 0.3*cm))

    # --- Financial Table ---
    table_data = [
        [Paragraph('<b>DESCRIPTION</b>', normal_style), Paragraph('<b>AMOUNT</b>', normal_style)],
        [Paragraph('<b>A. EARNINGS</b>', bold_style), ''],
        [f"Base Pay ({data.get('total_hours',0):.2f} Hrs)", f"{data.get('total_base_pay',0.0):.2f}"],
        [f"Overtime Pay", f"{data.get('total_overtime',0.0):.2f}"],
        [Paragraph('<b>GROSS PAY</b>', bold_style), Paragraph(f"<b>{data.get('gross_pay',0.0):.2f}</b>", bold_style)],
        [Paragraph('<b>B. STATUTORY DEDUCTIONS</b>', bold_style), '']
    ]
    for d in data.get('deductions_breakdown', []):
        table_data.append([d['name'].replace('_',' ').upper(), f"-{d['amount']:.2f}"])
    table_data.append([Paragraph('<b>C. ADVANCES / LOANS</b>', bold_style), ''])
    advances = data.get('advance_breakdown', [])
    if advances:
        for a in advances:
            table_data.append([f"Advance ({a.get('date','N/A')})", f"-{a['amount']:.2f}"])
    else:
        table_data.append(["No Advances", "0.00"])
    table_data.append([Paragraph('<b>NET PAYABLE</b>', bold_style),
                       Paragraph(f"<b>{data.get('net_pay',0.0):.2f} {data.get('currency','')}</b>", bold_style)])
    t = Table(table_data, colWidths=[page_width*0.75, page_width*0.25])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)

    # --- Signature ---
    story.append(Spacer(1, 1.5*cm))
    sig_data = [['Employee Signature: ____________________', 'Authorized By: ____________________']]
    sig_table = Table(sig_data, colWidths=[page_width/2, page_width/2])
    sig_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    story.append(sig_table)
    story.append(PageBreak())



# --- VIEWS ---

@csrf_exempt
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_generate_batch_payslips_pdf(request):
    """Generates a combined PDF for multiple users/months."""
    try:
        serializer = BatchPayslipSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        v = serializer.validated_data
        batch_result = PayrollService.generate_batch_payslips(
            user_ids=v['user_ids'],
            start_month=v['start_month'], start_year=v['start_year'],
            end_month=v['end_month'], end_year=v['end_year']
        )

        if batch_result.get("status") != "success" or not batch_result.get("data"):
            return Response({"status": "error", "message": "No data found for selection"}, status=404)

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm)
        story = []
        org = OrganizationDetail.objects.first()
        styles = getSampleStyleSheet()

        for payslip_data in batch_result["data"]:
            try:
                user = CustomUser.objects.get(user_id=payslip_data['user']['id'])
                _draw_payslip_page(story, user, payslip_data, org, styles)
            except CustomUser.DoesNotExist:
                continue

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Payroll_Batch_Export.pdf"'
        return response

    except Exception as e:
        Logs.atuta_technical_logger("batch_pdf_failed", exc_info=e)
        return Response({"status": "error", "message": str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_user_payslip_pdf(request):
    """Single PDF for the logged-in user."""
    user = request.user
    month = int(request.GET.get('month', datetime.date.today().month))
    year = int(request.GET.get('year', datetime.date.today().year))

    result = PayrollService.generate_detailed_payslip(user, month, year)
    if result["status"] != "success":
        return Response({"status": "error", "message": "Data not found"}, status=404)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    org = OrganizationDetail.objects.first()
    _draw_payslip_page(story, user, result["message"], org, getSampleStyleSheet())
    doc.build(story)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Payslip_{month}_{year}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_hour_corrections(request):
    """Fetch paginated hour adjustment records."""
    try:
        user_id = request.query_params.get('user_id')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        
        data = PayrollService.get_hour_corrections(
            user_id=user_id,
            month=int(month) if month else None,
            year=int(year) if year else None,
            page=int(request.query_params.get('page', 1)),
            per_page=int(request.query_params.get('per_page', 20))
        )
        return Response({"status": "success", "data": data})
    except Exception as e:
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def api_admin_record_hour_correction(request):
    """Admin: Manually add or deduct hours for a user's payroll."""
    try:
        user_id = request.data.get("user_id")
        hours = request.data.get("hours")
        reason = request.data.get("reason")
        
        if not all([user_id, hours is not None, reason]):
            return Response({"status": "error", "message": "missing_parameters"}, status=400)

        user = get_object_or_404(CustomUser, user_id=user_id)
        result = PayrollService.record_hour_correction(
            user=user,
            hours=float(hours),
            reason=reason,
            month=request.data.get("month"),
            year=request.data.get("year"),
            corrected_by=request.user
        )
        return Response(result, status=status.HTTP_200_OK if result["status"] == "success" else 400)
    except Exception as e:
        return Response({"status": "error", "message": "server_error"}, status=500)