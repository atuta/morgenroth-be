import datetime
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


@api_view(["GET"])
def api_generate_payroll_report(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # LOG 1: Check initial request parameters
    Logs.atuta_logger(f"1. API received start_date: {start_date}, end_date: {end_date}")

    # -------- VALIDATION --------
    if not start_date or not end_date:
        Logs.atuta_logger("2. Validation failed: start_date & end_date are required.")
        return HttpResponse("start_date & end_date are required", status=400)

    try:
        start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        
        Logs.atuta_logger(f"3. Dates parsed successfully: {start_date_obj} to {end_date_obj}")
        
    except Exception as e:
        Logs.atuta_logger(f"4. Date parsing error: {e}")
        return HttpResponse("Use YYYY-MM-DD date format", status=400)

    if end_date_obj < start_date_obj:
        Logs.atuta_logger("5. Validation failed: end_date cannot be before start_date.")
        return HttpResponse("end_date cannot be before start_date", status=400)

    try:
        # Step: Fetch report data
        report_data = UserService.generate_payroll_report(start_date_obj, end_date_obj)

        # --- Data Access ---
        report_message = report_data.get("message", {}) 
        employees = report_message.get("employees", [])
        totals = report_message.get("totals", {})
        currency = report_data.get("currency", "KES") 

        # LOG 6 & 7 (omitted for brevity, but they are logically correct now)
        
        # ==================== PDF BUILDING ====================
        buffer = BytesIO()
        
        LEFT_MARGIN = 1.5 * cm
        RIGHT_MARGIN = 1.5 * cm
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            topMargin=1.5*cm, bottomMargin=1.5*cm,
            leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN
        )
        
        # Calculate available width (A4 width (landscape) is 29.7cm)
        # landscape(A4)[0] is the width (29.7cm)
        AVAILABLE_WIDTH = landscape(A4)[0] - LEFT_MARGIN - RIGHT_MARGIN
        
        # Define column ratios (Total of 1.0)
        # Employee Name needs the most space, others are fixed monetary values.
        EMPLOYEE_COL_RATIO = 0.35  # 35% of the width
        MONEY_COL_RATIO = (1.0 - EMPLOYEE_COL_RATIO) / 4 # Remaining 65% divided among 4 money columns

        # Column Widths calculation
        col_widths = [
            EMPLOYEE_COL_RATIO * AVAILABLE_WIDTH,  # Employee
            MONEY_COL_RATIO * AVAILABLE_WIDTH,     # Gross Pay
            MONEY_COL_RATIO * AVAILABLE_WIDTH,     # Deductions
            MONEY_COL_RATIO * AVAILABLE_WIDTH,     # Advances
            MONEY_COL_RATIO * AVAILABLE_WIDTH,     # Net Pay
        ]
        # ---------------------------------------------
        
        styles = getSampleStyleSheet()
        Title = styles['Title']; Title.alignment = 1
        Bold = ParagraphStyle('Bold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11)
        Normal_Right = ParagraphStyle('Normal_Right', parent=styles['Normal'], alignment=2)
        Bold_Right = ParagraphStyle('Bold_Right', parent=Bold, alignment=2)
        Normal = styles['Normal']

        Story = []
        Story.append(Paragraph("Morgenroth Schulhaus", Title))
        Story.append(Paragraph("<b>Payroll Summary Report</b>", Bold))
        Story.append(Paragraph(f"Period: {start_date} → {end_date}", Normal))
        Story.append(Spacer(1, 0.5*cm))

        # ---------- MAIN TABLE ----------
        header = ["Employee", "Gross Pay", "Deductions", "Advances", "Net Pay"]
        table_data = [[Paragraph(f"<b>{h}</b>", Bold) for h in header]]

        for emp in employees:
            s = emp["summary"]
            table_data.append([
                Paragraph(emp["user"]["full_name"], Normal),
                Paragraph(f"{s['gross_pay']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['total_deductions']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['total_advance']:.2f} {currency}", Normal_Right),
                Paragraph(f"{s['net_pay']:.2f} {currency}", Normal_Right),
            ])

        # Totals row
        table_data.append([
            Paragraph("<b>TOTALS</b>", Bold),
            Paragraph(f"{totals.get('gross_pay', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('total_deductions', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('total_advance', 0):.2f} {currency}", Bold_Right),
            Paragraph(f"{totals.get('net_pay', 0):.2f} {currency}", Bold_Right),
        ])

        # Apply the new dynamic colWidths
        table = Table(table_data, colWidths=col_widths) 
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#E6E6E6")),
            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor("#B4E1FA")),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ]))
        Story.append(table)
        
        Logs.atuta_logger("10. Attempting to build PDF document.")

        doc.build(Story)
        
        Logs.atuta_logger("11. PDF built successfully.")


        # ==================== SAVE LOCALLY ====================
        reports_dir = os.path.join(settings.BASE_DIR, "payroll_reports")
        os.makedirs(reports_dir, exist_ok=True)

        file_path = os.path.join(
            reports_dir,
            f"Payroll_Report_{start_date}_{end_date}.pdf"
        )

        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())

        Logs.atuta_logger(f"12. PDF saved locally at: {file_path}")

        # ==================== RETURN FILE =====================
        pdf_bytes = buffer.getvalue()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Length'] = len(pdf_bytes)
        response['Content-Disposition'] = f'attachment; filename=\"Payroll_Report_{start_date}_{end_date}.pdf\"'
        
        Logs.atuta_logger("13. Payroll report HTTP response generated and returned.")

        return response

    except Exception as e:
        # LOG 14: Catch-all logging for unexpected failures
        error_message = f"An unexpected error occurred during PDF generation: {e}"
        Logs.atuta_technical_logger(error_message, exc_info=e)
        return HttpResponse("Payroll PDF generation failed", status=500)