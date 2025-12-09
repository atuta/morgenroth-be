import datetime
from io import BytesIO

from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework import serializers
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Reportlab Imports for PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

# Application Specific Imports (Assuming these paths are correct)
from mapp.models import CustomUser
from mapp.classes.payroll_service import PayrollService
from mapp.classes.logs.logs import Logs


# --- DRF PERMISSIONS AND SERIALIZERS ---

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow users with 'admin' role to access the view.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.user_role == 'admin'


class PayslipQuerySerializer(serializers.Serializer):
    """
    Serializer to validate month, year, and optionally user_id query parameters.
    """
    today = datetime.date.today()
    month = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
        default=today.month
    )
    year = serializers.IntegerField(
        required=False,
        min_value=2000,
        max_value=today.year,
        default=today.year
    )
    user_id = serializers.CharField(
        required=False, 
        help_text="Required for admin endpoints to specify target user."
    )


# --- HELPER FUNCTIONS (Service Logic) ---

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
    Helper function to create PDF in memory using a SINGLE Consolidated Table,
    ensuring full width and clear total presentation, and adds a signature block.
    """
    buffer = BytesIO()
    
    # 1. Setup Document and Styles
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
    )
    styles = getSampleStyleSheet()
    
    h1 = styles['h1']
    h1.alignment = 1 
    h1.spaceAfter = 0.5*cm
    
    # Define a simple bold style based on Normal text (replaces old h2 for sections)
    bold_style = ParagraphStyle(
        'BoldNormal', 
        parent=styles['Normal'], 
        fontName='Helvetica-Bold', 
        fontSize=12,
        spaceAfter=0.1*cm,
        spaceBefore=0.2*cm,
    )
    
    # Define a style for the final NET PAY to keep it prominent
    final_pay_style = ParagraphStyle(
        'FinalPay', 
        parent=bold_style, 
        fontSize=14, 
    )
    
    Story = []

    # Title and General Information Header (Retained)
    Story.append(Paragraph(data["organization"], h1))
    Story.append(Paragraph("<b>OFFICIAL PAYSLIP</b>", bold_style))
    Story.append(Paragraph(f"<b>For:</b> {user.full_name} ({user.email})", styles['Normal']))
    Story.append(Paragraph(f"<b>Period:</b> {month}/{year}", styles['Normal']))
    Story.append(Paragraph(f"<b>Hourly Rate:</b> {data['hourly_rate']} {data['currency']}", styles['Normal']))
    Story.append(Paragraph(f"<b>Total Hours:</b> {data.get('total_hours', 0.0):.2f}", styles['Normal']))
    Story.append(Spacer(1, 0.5*cm))

    # Calculate page width for full-width table
    page_width = A4[0] - 3*cm 

    # 2. Build Consolidated Table Data
    
    table_data = [
        [Paragraph('<b>DESCRIPTION</b>', styles['Normal']), Paragraph('<b>AMOUNT</b>', styles['Normal'])]
    ]
    
    currency = data['currency']
    row_count = 0

    # --- CALCULATIONS AND SECTION INDEXING ---
    
    total_base_pay = data.get('total_base_pay', 0.0)
    total_overtime = data.get('total_overtime', 0.0)
    total_deductions = data.get('total_deductions', 0.0)
    total_advance = data.get('total_advance', 0.0)
    net_pay = data.get('net_pay', 0.0)


    # --- A. EARNINGS SECTION ---
    row_count += 1
    earnings_header_row = row_count
    table_data.append([Paragraph('<b>A. EARNINGS</b>', bold_style), '']) 
    
    # Base Pay
    row_count += 1
    table_data.append([
        f"Base Pay ({data.get('total_hours', 0.0):.2f} Hours)",
        f"{total_base_pay:.2f} {currency}"
    ])
    
    # Overtime (ALWAYS INCLUDED)
    row_count += 1
    table_data.append([
        f"Overtime Pay",
        f"{total_overtime:.2f} {currency}" 
    ])

    # Gross Pay Subtotal
    gross_pay = total_base_pay + total_overtime
    row_count += 1
    gross_subtotal_row = row_count
    table_data.append([
        Paragraph('<b>GROSS PAY (TOTAL EARNINGS)</b>', styles['Normal']), 
        Paragraph(f'<b>{gross_pay:.2f} {currency}</b>', styles['Normal'])
    ])
    
    # --- B. DEDUCTIONS SECTION ---
    row_count += 1
    deduction_header_row = row_count
    table_data.append([Paragraph('<b>B. STATUTORY DEDUCTIONS</b>', bold_style), ''])
    
    if data.get("deductions_breakdown"):
        for item in data["deductions_breakdown"]:
            raw_name = item.get("name", "Deduction")
            formatted_name = raw_name.replace('_', ' ').upper()
            
            percent = item.get("percentage", 0)
            amount = item.get("amount", 0.0)
            
            row_count += 1
            table_data.append([
                f"{formatted_name} ({percent:.1f}%)",
                f"-{amount:.2f} {currency}"
            ])
    else:
        row_count += 1
        table_data.append(["No Statutory Deductions for this period", ""])
        
    # --- C. ADVANCES SECTION (Always included, even if total is 0) ---
    row_count += 1
    advance_header_row = row_count
    table_data.append([Paragraph('<b>C. ADVANCES / LOANS</b>', bold_style), ''])
    
    if total_advance > 0 and data.get("advance_breakdown"):
        for item in data["advance_breakdown"]:
            date = item.get("date", "N/A")
            approved_by = item.get("approved_by", "N/A")
            amount = item.get("amount", 0.0)
            
            row_count += 1
            table_data.append([
                f"Advance ({date}, Approved by: {approved_by})",
                f"-{amount:.2f} {currency}"
            ])
    else:
        row_count += 1
        table_data.append(["No Advances or Loans outstanding", ""])
            
    # --- D. NET PAY SUMMARY ---
    row_count += 1
    table_data.append([Spacer(1, 0.2*cm), Spacer(1, 0.2*cm)]) 
    
    row_count += 1
    net_pay_row = row_count
    table_data.append([
        Paragraph('<b>NET PAY (FINAL AMOUNT)</b>', final_pay_style),
        Paragraph(f'<b>{net_pay:.2f} {currency}</b>', final_pay_style)
    ])


    # 3. Define and Apply Table Style
    
    col_widths = [page_width * 0.75, page_width * 0.25] 
    table = Table(table_data, colWidths=col_widths)
    
    # Base Style Commands
    style_commands = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6), 
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10), 

        # Header Row (Row 0)
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EFEFEF')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'), 

        # Section Headers 
        ('SPAN', (0, earnings_header_row), (1, earnings_header_row)),
        ('BACKGROUND', (0, earnings_header_row), (-1, earnings_header_row), colors.HexColor("#BFDDF0")),
        
        ('SPAN', (0, deduction_header_row), (1, deduction_header_row)),
        ('BACKGROUND', (0, deduction_header_row), (-1, deduction_header_row), colors.HexColor('#CCCCCC')),
        
        ('SPAN', (0, advance_header_row), (1, advance_header_row)),
        ('BACKGROUND', (0, advance_header_row), (-1, advance_header_row), colors.HexColor('#CCCCCC')),
        
        # Gross Pay Subtotal 
        ('LINEBELOW', (0, gross_subtotal_row), (-1, gross_subtotal_row), 1, colors.black), 
        ('FONTNAME', (0, gross_subtotal_row), (-1, gross_subtotal_row), 'Helvetica-Bold'),

        # Net Pay Row
        ('BACKGROUND', (0, net_pay_row), (-1, net_pay_row), colors.HexColor('#BFDDF0')),
        ('LINEBELOW', (0, net_pay_row), (-1, net_pay_row), 2, colors.black),
        ('FONTNAME', (0, net_pay_row), (-1, net_pay_row), 'Helvetica-Bold'),
    ]

    table.setStyle(TableStyle(style_commands))
    Story.append(table)
    
    
    # 4. Add Signature Block
    Story.append(Spacer(1, 1.5*cm)) # Significant space after the main financial table

    # Signature line data, spanning the full width
    signature_data = [
        ['Signed By: _________________________________', 'Date: _________________________________']
    ]
    
    sig_col_widths = [page_width / 2.0, page_width / 2.0] # Split the width equally
    signature_table = Table(signature_data, colWidths=sig_col_widths)
    
    # Style the signature block (no borders, simple formatting)
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # Left side (Signed By) left aligned
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'), # Right side (Date) right aligned
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    
    Story.append(signature_table)

    # 5. Build PDF
    doc.build(Story)
    buffer.seek(0)
    return buffer


# --- DRF VIEWS (Unified with _handle_payslip_generation) ---

def _handle_payslip_generation(request, is_admin_view=False, is_pdf=False):
    """
    Unified handler for all four payslip endpoints.
    """
    # 1. Validate Query Parameters
    serializer = PayslipQuerySerializer(data=request.GET)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    validated_data = serializer.validated_data
    month = validated_data['month']
    year = validated_data['year']
    
    # 2. Determine Target User
    user = request.user
    if is_admin_view:
        user_id = validated_data.get("user_id")
        if not user_id:
            return Response(
                {"status": "error", "message": "user_id query parameter is required for admin endpoints"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            # Note: This user object is an instance of CustomUser, which has the full_name property.
            user = get_object_or_404(CustomUser, user_id=user_id)
        except Http404:
             return Response(
                {"status": "error", "message": f"User with ID '{user_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

    try:
        # 3. Generate Payslip Data
        data = _generate_payslip_data(user, month, year)
        if not data:
            error_msg = "Failed to generate payslip data. Check if payroll data exists for this period."
            if is_pdf:
                 return HttpResponse(error_msg, status=400)
            return Response({"status": "error", "message": error_msg}, status=400)

        # 4. Handle PDF or JSON Response
        if is_pdf:
            buffer = _generate_payslip_pdf(user, data, month, year)
            
            # --- FIX FOR DOWNLOAD ISSUE START ---
            pdf_bytes = buffer.getvalue()
            
            # Create the response with the byte content
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            
            # Set the Content-Length header to help the browser start the download
            response['Content-Length'] = len(pdf_bytes)
            # --- FIX FOR DOWNLOAD ISSUE END ---

            # Sanitize filename (Uses user.full_name from the CustomUser model)
            filename = f"Payslip_{user.full_name.replace(' ', '_')}_{month}_{year}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        else:
            return Response({"status": "success", "message": "Payslip generated successfully", "data": data})

    except Exception as e:
        # 5. Log Error and Return 500
        endpoint_name = ("admin_" if is_admin_view else "") + "generate_user_payslip" + ("_pdf" if is_pdf else "")
        Logs.atuta_technical_logger(
            f"{endpoint_name}_failed_user_{user.user_id}_{month}_{year}",
            exc_info=e
        )
        server_error_msg = "Payslip generation failed due to a server error."
        if is_pdf:
            return HttpResponse(server_error_msg, status=500)
        return Response({"status": "error", "message": server_error_msg}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_user_payslip(request):
    """ JSON payslip for the logged-in user. """
    return _handle_payslip_generation(request, is_admin_view=False, is_pdf=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_user_payslip_pdf(request):
    """ PDF payslip for the logged-in user. """
    return _handle_payslip_generation(request, is_admin_view=False, is_pdf=True)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_generate_user_payslip(request):
    """ Admin-facing JSON payslip endpoint. Requires ?user_id=... """
    return _handle_payslip_generation(request, is_admin_view=True, is_pdf=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_generate_user_payslip_pdf(request):
    """ Admin-facing PDF payslip endpoint. Requires ?user_id=... """
    return _handle_payslip_generation(request, is_admin_view=True, is_pdf=True)