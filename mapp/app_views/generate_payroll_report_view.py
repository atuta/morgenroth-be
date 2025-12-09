import datetime
import traceback
from io import BytesIO
import os
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from mapp.classes.user_service import UserService
from mapp.classes.logs.logs import Logs


# Helper function to format snake_case to ALL UPPERCASE (e.g., housing_levy -> HOUSING LEVY)
def format_deduction_name(name):
    """Converts snake_case string to ALL UPPERCASE with spaces."""
    return name.replace('_', ' ').upper()


# Helper function to build the detail tables
def build_detail_table(header_text, detail_items, currency, NormalStyle, NormalRightStyle, DetailStyle, DetailHeaderRightStyle, width):
    """
    Creates a nested table for specific transaction details (Advances, Deductions, Overtime).
    """
    if not detail_items:
        return []

    Story = []
    detail_data = []
    style_commands = []
    
    if header_text == "Deductions":
        detail_header = [Paragraph("Name", DetailStyle), Paragraph("Rate", DetailStyle), Paragraph("Amount", DetailHeaderRightStyle)]
        col_widths = [0.3 * width, 0.2 * width, 0.5 * width]
        
        detail_data = [
            [
                Paragraph(format_deduction_name(item["name"]), NormalStyle),
                Paragraph(f"{item.get('percentage', 0):.2f}%", NormalStyle),
                Paragraph(f"{item['amount']:.2f} {currency}", NormalRightStyle),
            ] for item in detail_items if item.get('amount', 0) > 0
        ]
        # Amount is the last column (index -1), handled below
        
    elif header_text == "Overtime":
        # Amount is the 3rd column (index 2), Remarks is the last column
        detail_header = [Paragraph("Date", DetailStyle), Paragraph("Hours", DetailStyle), Paragraph("Amount", DetailHeaderRightStyle), Paragraph("Remarks", DetailStyle)]
        col_widths = [0.2 * width, 0.15 * width, 0.25 * width, 0.4 * width]
        
        detail_data = [
            [
                Paragraph(item.get("date", "N/A"), NormalStyle),
                Paragraph(f"{item.get('hours', 0):.1f}", NormalStyle),
                Paragraph(f"{item['amount']:.2f} {currency}", NormalRightStyle),
                Paragraph(item.get("remarks", ""), NormalStyle),
            ] for item in detail_items if item.get('amount', 0) > 0
        ]
        style_commands = [('ALIGN', (2, 1), (2, -1), 'RIGHT')]
        
    elif header_text == "Advances":
        # Amount is the 2nd column (index 1), Approved By is the last column
        detail_header = [Paragraph("Date", DetailStyle), Paragraph("Amount", DetailHeaderRightStyle), Paragraph("Remarks", DetailStyle), Paragraph("Approved By", DetailStyle)]
        col_widths = [0.2 * width, 0.2 * width, 0.3 * width, 0.3 * width]
        
        detail_data = [
            [
                Paragraph(item.get("date", "N/A"), NormalStyle),
                Paragraph(f"{item['amount']:.2f} {currency}", NormalRightStyle),
                Paragraph(item.get("remarks", ""), NormalStyle),
                Paragraph(item.get("approved_by", "N/A"), NormalStyle),
            ] for item in detail_items if item.get('amount', 0) > 0
        ]
        style_commands = [('ALIGN', (1, 1), (1, -1), 'RIGHT')]
    
    if not detail_data:
        return []

    Story.append(Paragraph(f"<b>--- {header_text.upper()} DETAILS ---</b>", DetailStyle))
    detail_data.insert(0, detail_header)

    detail_table = Table(detail_data, colWidths=col_widths)
    
    # Base styles for all detail tables
    base_styles = [
        ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]
    
    # Add manual alignment commands for Overtime and Advances
    if header_text in ["Overtime", "Advances"]:
        base_styles.extend(style_commands)
        
    # Crucial: Apply right alignment to the last column for Deductions
    if header_text == "Deductions":
        base_styles.append(('ALIGN', (-1, 1), (-1, -1), 'RIGHT')) 

    detail_table.setStyle(TableStyle(base_styles))
    
    Story.append(Spacer(1, 0.1*cm))
    Story.append(detail_table)
    Story.append(Spacer(1, 0.3*cm))
    
    return Story


@api_view(["GET"])
def api_generate_payroll_report(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # --- Initial Validation ---
    if not start_date or not end_date: return HttpResponse("start_date & end_date are required", status=400)
    try:
        start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except: return HttpResponse("Use YYYY-MM-DD date format", status=400)
    if end_date_obj < start_date_obj: return HttpResponse("end_date cannot be before start_date", status=400)

    try:
        # Step: Fetch report data
        report_data = UserService.generate_payroll_report(start_date_obj, end_date_obj)
        report_message = report_data.get("message", {}) 
        employees = report_message.get("employees", [])
        totals = report_message.get("totals", {})
        currency = report_data.get("currency", "KES") 

        # ==================== PDF BUILDING SETUP ====================
        buffer = BytesIO()
        
        LEFT_MARGIN = 1.5 * cm
        RIGHT_MARGIN = 1.5 * cm
        AVAILABLE_WIDTH = landscape(A4)[0] - LEFT_MARGIN - RIGHT_MARGIN
        EMPLOYEE_COL_RATIO = 0.35
        MONEY_COL_RATIO = (1.0 - EMPLOYEE_COL_RATIO) / 4
        
        col_widths = [
            EMPLOYEE_COL_RATIO * AVAILABLE_WIDTH, MONEY_COL_RATIO * AVAILABLE_WIDTH,
            MONEY_COL_RATIO * AVAILABLE_WIDTH, MONEY_COL_RATIO * AVAILABLE_WIDTH,
            MONEY_COL_RATIO * AVAILABLE_WIDTH,
        ]
        
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4), topMargin=1.5*cm, bottomMargin=1.5*cm,
            leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN
        )

        # --- ReportLab Styles ---
        styles = getSampleStyleSheet()
        Title = styles['Title']; Title.alignment = 1
        Bold = ParagraphStyle('Bold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11)
        Normal_Right = ParagraphStyle('Normal_Right', parent=styles['Normal'], alignment=2) 
        Bold_Right = ParagraphStyle('Bold_Right', parent=Bold, alignment=2)
        Bold_Right_Header = ParagraphStyle('Bold_Right_Header', parent=Bold, alignment=2) # Used for 'Net Pay' Title
        Normal = styles['Normal']
        DetailHeaderRightStyle = ParagraphStyle('DetailHeaderRight', parent=Bold, fontSize=8, alignment=2, textColor=colors.darkgrey)
        DetailStyle = ParagraphStyle('Detail', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.darkgrey)

        Story = []
        Story.append(Paragraph("Morgenroth Schulhaus", Title))
        Story.append(Paragraph("<b>Payroll Summary Report</b>", Bold))
        Story.append(Paragraph(f"Period: {start_date} → {end_date}", Normal))
        Story.append(Spacer(1, 0.5*cm))

        # --- MAIN TABLE CONSTRUCTION ---
        header = ["Employee", "Gross Pay", "Deductions", "Advances", "Net Pay"]
        
        # 1. Header Row (Applying Bold_Right_Header to the last column)
        table_data = [[
            Paragraph(f"<b>{header[0]}</b>", Bold),
            Paragraph(f"<b>{header[1]}</b>", Bold),
            Paragraph(f"<b>{header[2]}</b>", Bold),
            Paragraph(f"<b>{header[3]}</b>", Bold),
            Paragraph(f"<b>{header[4]}</b>", Bold_Right_Header),
        ]]
        
        for emp in employees:
            s = emp["summary"]
            
            # 2. Main Summary Row
            summary_row = [
                Paragraph(emp["user"]["full_name"], Bold),
                Paragraph(f"{s['gross_pay']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['total_deductions']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['total_advance']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['net_pay']:.2f} {currency}", Bold_Right),
            ]
            
            # 3. Build Nested Details
            detail_cell_contents = []
            detail_width = AVAILABLE_WIDTH * 0.9 
            
            detail_cell_contents.extend(
                build_detail_table("Overtime", emp.get("overtime", []), currency, Normal, Normal_Right, DetailStyle, DetailHeaderRightStyle, detail_width)
            )
            detail_cell_contents.extend(
                build_detail_table("Advances", emp.get("advances", []), currency, Normal, Normal_Right, DetailStyle, DetailHeaderRightStyle, detail_width)
            )
            detail_cell_contents.extend(
                build_detail_table("Deductions", emp.get("deductions", []), currency, Normal, Normal_Right, DetailStyle, DetailHeaderRightStyle, detail_width)
            )
            
            table_data.append(summary_row)

            if detail_cell_contents:
                detail_row = [[detail_cell_contents, Paragraph("", Normal), Paragraph("", Normal), Paragraph("", Normal), Paragraph("", Normal)]]
                table_data.extend(detail_row)


        # 4. Totals row (Uses Bold_Right for final alignment)
        table_data.append([
            Paragraph("<b>TOTALS</b>", Bold),
            Paragraph(f"{totals.get('gross_pay', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('total_deductions', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('total_advance', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('net_pay', 0):.2f} {currency}", Bold_Right),
        ])

        # 5. Table Styling and SPAN Logic
        style_list = [
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#E6E6E6")),
            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor("#B4E1FA")),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
            # Ensure the Net Pay column (index -1) content is right aligned 
            ('ALIGN', (-1, 1), (-1, -2), 'RIGHT'), 
        ]

        # Dynamic SPAN for detail rows
        for i in range(1, len(table_data) - 1): 
            if isinstance(table_data[i][0], list): 
                style_list.append(('SPAN', (0, i), (-1, i)))
                style_list.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#FFFFFF")))
                style_list.append(('LEFTPADDING', (0, i), (-1, i), 0))
                style_list.append(('RIGHTPADDING', (0, i), (-1, i), 0))
                style_list.append(('TOPPADDING', (0, i), (-1, i), 0))
                style_list.append(('BOTTOMPADDING', (0, i), (-1, i), 0))

        table = Table(table_data, colWidths=col_widths, repeatRows=1) 
        table.setStyle(TableStyle(style_list))
        
        Story.append(table)
        Story.append(Spacer(1, 0.5*cm))
        
        # 6. Build PDF, Save, and Return HTTP Response
        doc.build(Story)
        
        reports_dir = os.path.join(settings.BASE_DIR, "payroll_reports")
        os.makedirs(reports_dir, exist_ok=True)

        file_path = os.path.join(
            reports_dir,
            f"Payroll_Report_{start_date}_{end_date}.pdf"
        )

        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())

        pdf_bytes = buffer.getvalue()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Length'] = len(pdf_bytes)
        response['Content-Disposition'] = f'attachment; filename=\"Payroll_Report_{start_date}_{end_date}.pdf\"'

        return response

    except Exception as e:
        # Robust Error Handling
        error_message = f"An unexpected error occurred during PDF generation: {e}"
        Logs.atuta_technical_logger(error_message, exc_info=e) 
        return HttpResponse(
            "An internal server error occurred during report generation. Please check the system logs.", 
            status=500
        )