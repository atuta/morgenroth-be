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
    Constructs the visual elements for a single payslip page.
    Handles Earnings, Overtime, Hour Corrections, Deductions, and Advances.
    """
    page_width = A4[0] - 3*cm
    bold_style = ParagraphStyle('BoldNormal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['h2'], alignment=1)

    # 1. Branding Header
    if org and org.logo:
        try:
            # Safely handle logo path
            logo = Image(org.logo.path, width=2.2*cm, height=2.2*cm)
            logo.hAlign = 'LEFT'
            story.append(logo)
        except Exception:
            pass

    org_name = org.name if org else "Official Organization"
    story.append(Paragraph(f"<font size=14><b>{org_name.upper()}</b></font>", styles['Normal']))
    if org and org.physical_address:
        story.append(Paragraph(org.physical_address, styles['Normal']))
    
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("OFFICIAL PAYSLIP", header_style))
    story.append(Spacer(1, 0.4*cm))
    
    # 2. Employee Info Table
    info_data = [
        [f"Employee: {user.full_name}", f"Period: {data['month']}/{data['year']}"],
        [f"ID/No: {getattr(user, 'id_number', 'N/A')}", f"Rate: {data['hourly_rate']} {data['currency']}/hr"]
    ]
    info_table = Table(info_data, colWidths=[page_width*0.6, page_width*0.4])
    info_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (-1,-1), 0), ('FONTSIZE', (0,0), (-1,-1), 10)]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # 3. Financial Table Data Construction
    table_data = [[Paragraph('<b>DESCRIPTION</b>', bold_style), Paragraph('<b>AMOUNT</b>', bold_style)]]
    
    # --- A. EARNINGS & ADJUSTMENTS ---
    table_data.append([Paragraph('<b>A. EARNINGS & ADJUSTMENTS</b>', bold_style), ''])
    table_data.append([f"Base Pay ({data.get('total_hours', 0):.2f} Hrs)", f"{data['total_base_pay']:.2f}"])
    
    if data.get('total_overtime', 0) > 0:
        table_data.append([f"Overtime Pay", f"{data['total_overtime']:.2f}"])
    
    # Capture Hour Corrections from Service (Dynamic)
    correction_amt = data.get('hour_correction_total', 0)
    if correction_amt != 0:
        label = "Hour Correction (Add)" if correction_amt > 0 else "Hour Correction (Deduct)"
        table_data.append([label, f"{correction_amt:.2f}"])

    table_data.append([Paragraph('<b>GROSS PAY</b>', bold_style), Paragraph(f"<b>{data['gross_pay']:.2f}</b>", bold_style)])

    # --- B. STATUTORY DEDUCTIONS ---
    table_data.append([Paragraph('<b>B. STATUTORY DEDUCTIONS</b>', bold_style), ''])
    deductions = data.get('deductions_breakdown', [])
    if deductions:
        for d in deductions:
            name = d['name'].replace('_', ' ').upper()
            table_data.append([name, f"-{d['amount']:.2f}"])
    else:
        table_data.append(["No Statutory Deductions", "0.00"])

    # --- C. ADVANCES / LOANS ---
    table_data.append([Paragraph('<b>C. ADVANCES / LOANS</b>', bold_style), ''])
    advances = data.get('advance_breakdown', [])
    if advances:
        for a in advances:
            table_data.append([f"Advance ({a.get('date', 'N/A')})", f"-{a['amount']:.2f}"])
    else:
        table_data.append(["No Advances Outstanding", "0.00"])

    # --- NET PAY ---
    table_data.append([
        Paragraph('<font size=11><b>NET PAYABLE</b></font>', bold_style), 
        Paragraph(f"<b>{data['net_pay']:.2f} {data['currency']}</b>", bold_style)
    ])

    # 4. Table Styling
    t = Table(table_data, colWidths=[page_width * 0.7, page_width * 0.3])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
        ('BACKGROUND', (0,1), (1,1), colors.HexColor("#BFDDF0")), # Earnings blue
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 1.5*cm))
    
    # 5. Signatures
    sig_data = [['Employee Signature: ____________________', 'Authorized By: ____________________']]
    sig_table = Table(sig_data, colWidths=[page_width/2, page_width/2])
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