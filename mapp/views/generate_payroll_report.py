# Standard Imports
import datetime
from io import BytesIO

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# ReportLab Imports
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

# Application Imports
from mapp.classes.user_service import UserService
from mapp.classes.logs.logs import Logs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_generate_payroll_report(request):
    """
    Generate company payroll report for a date range.
    Returns JSON or PDF depending on 'format' query parameter.

    Required query params:
        - start_date (YYYY-MM-DD)
        - end_date   (YYYY-MM-DD)
        - format     (json or pdf, default=json)
    """

    # ---------------------- validate inputs ----------------------
    start_date = request.GET.get("start_date")
    end_date   = request.GET.get("end_date")
    response_format = request.GET.get("format", "json").lower()

    if not start_date or not end_date:
        return Response({"status":"error","message":"start_date and end_date are required"}, status=400)

    try:
        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date   = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except Exception:
        return Response({"status":"error","message":"Invalid date format. Use YYYY-MM-DD"}, status=400)

    if end_date < start_date:
        return Response({"status":"error","message":"end_date cannot be before start_date"}, status=400)

    # ---------------------- generate report data ----------------------
    try:
        report_data = UserService.generate_payroll_report(start_date, end_date)  # returns dict with "employees" and "totals"

        # ---------------- JSON RESPONSE ----------------
        if response_format == "json":
            return Response({
                "status": "success",
                "range": {"start_date": str(start_date), "end_date": str(end_date)},
                "employees": report_data.get("employees", []),
                "totals": report_data.get("totals", {})
            })

        # ---------------- PDF RESPONSE ----------------
        elif response_format == "pdf":
            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=landscape(A4),
                topMargin=1.5*cm,
                bottomMargin=1.5*cm,
                leftMargin=1.5*cm,
                rightMargin=1.5*cm
            )
            Story = []

            # --- Styles ---
            styles = getSampleStyleSheet()
            h1 = styles['Title']
            h1.alignment = 1
            h1.spaceAfter = 0.5*cm

            bold_style = ParagraphStyle(
                'BoldNormal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, spaceAfter=0.1*cm
            )
            normal_style = styles['Normal']

            # --- Header ---
            Story.append(Paragraph("Morgenroth Schulhaus", h1))
            Story.append(Paragraph(f"Payroll Report", bold_style))
            Story.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
            Story.append(Spacer(1, 0.5*cm))

            # --- Main Summary Table ---
            table_data = [
                [
                    Paragraph("<b>Employee</b>", normal_style),
                    Paragraph("<b>Gross Pay</b>", normal_style),
                    Paragraph("<b>Total Deductions</b>", normal_style),
                    Paragraph("<b>Total Advances</b>", normal_style),
                    Paragraph("<b>Net Pay</b>", normal_style),
                ]
            ]

            currency = report_data.get("currency", "KES")

            for emp in report_data.get("employees", []):
                summary = emp['summary']
                table_data.append([
                    emp['user']['full_name'],
                    f"{summary['gross_pay']:.2f} {currency}",
                    f"{summary['total_deductions']:.2f} {currency}",
                    f"{summary['total_advance']:.2f} {currency}",
                    f"{summary['net_pay']:.2f} {currency}",
                ])

            # Optional: Totals row
            totals = report_data.get("totals", {})
            table_data.append([
                Paragraph("<b>Totals</b>", bold_style),
                f"{totals.get('gross_pay', 0.0):.2f} {currency}",
                f"{totals.get('total_deductions', 0.0):.2f} {currency}",
                f"{totals.get('total_advance', 0.0):.2f} {currency}",
                f"{totals.get('net_pay', 0.0):.2f} {currency}",
            ])

            # Table column widths
            col_widths = [8*cm, 4*cm, 4*cm, 4*cm, 4*cm]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EFEFEF')),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#BFDDF0')),
            ]))
            Story.append(table)
            Story.append(Spacer(1, 0.5*cm))

            # --- Detailed Tables per Employee ---
            for emp in report_data.get("employees", []):
                Story.append(Paragraph(f"Details for {emp['user']['full_name']}", bold_style))
                Story.append(Spacer(1, 0.2*cm))

                # Function to build a mini-table
                def build_mini_table(title, items, columns):
                    if not items:
                        return
                    Story.append(Paragraph(title, bold_style))
                    mini_data = [columns]
                    for item in items:
                        row = [str(item.get(col.lower(), "")) for col in columns]
                        mini_data.append(row)
                    mini_table = Table(mini_data, colWidths=[5*cm if i==0 else 4*cm for i in range(len(columns))])
                    mini_table.setStyle(TableStyle([
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EFEFEF')),
                        ('ALIGN', (1,1), (-1,-1), 'RIGHT')
                    ]))
                    Story.append(mini_table)
                    Story.append(Spacer(1, 0.3*cm))

                # Attendance Table
                build_mini_table(
                    "Attendance",
                    emp.get("attendance", []),
                    ["Date", "Hours", "Pay", "Notes"]
                )
                # Overtime Table
                build_mini_table(
                    "Overtime",
                    emp.get("overtime", []),
                    ["Date", "Hours", "Amount", "Remarks"]
                )
                # Deductions Table
                build_mini_table(
                    "Deductions",
                    emp.get("deductions", []),
                    ["Name", "Percentage", "Amount"]
                )
                # Advances Table
                build_mini_table(
                    "Advance Payments",
                    emp.get("advances", []),
                    ["Date", "Amount", "Remarks", "Approved_by"]
                )
                Story.append(Spacer(1, 0.5*cm))

            # Optional: Signature block
            signature_data = [['Signed By: ________________________', 'Date: ________________________']]
            sig_table = Table(signature_data, colWidths=[(landscape(A4)[0]-3*cm)/2]*2)
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (0,0), 'LEFT'),
                ('ALIGN', (1,0), (1,0), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            Story.append(sig_table)

            # Build PDF
            doc.build(Story)
            pdf_buffer.seek(0)
            response = HttpResponse(pdf_buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Payroll_Report_{start_date}_{end_date}.pdf"'
            response['Content-Length'] = pdf_buffer.getbuffer().nbytes
            return response

        else:
            return Response({"status":"error","message":"Invalid format. Use json or pdf"}, status=400)

    except Exception as e:
        Logs.atuta_technical_logger(f"api_generate_payroll_report_failed_{start_date}_{end_date}", exc_info=e)
        return Response({"status":"error","message":"Payroll report generation failed"}, status=500)
