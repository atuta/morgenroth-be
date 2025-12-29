# 1. Python Standard Library
import datetime
import traceback
import os
from io import BytesIO

# 2. Third-Party Libraries
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, 
    Table, TableStyle, Image, KeepTogether
)

# 3. Django Core
from django.conf import settings
from django.http import HttpResponse
from rest_framework.response import Response

# 4. Django Rest Framework (DRF)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

# 5. Local Project Imports (mapp)
from mapp.classes.attendance_service import AttendanceService
from mapp.models import AttendanceSession
from mapp.classes.logs.logs import Logs

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_generate_attendance_pdf(request):
    """
    Generates a detailed attendance report PDF with dates on every row 
    and highlighted daily totals at the bottom of each date group.
    """
    user_id = request.GET.get("user_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if not all([user_id, start_date, end_date]):
        return HttpResponse("user_id, start_date & end_date are required", status=400)
    
    try:
        start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponse("Use YYYY-MM-DD date format", status=400)

    try:
        report_data = AttendanceService.get_detailed_attendance_report(user_id, start_date, end_date)
        if not report_data:
            return HttpResponse("No data found for the selected user and range", status=404)

        user_info = report_data.get("user", {})
        summary = report_data.get("summary", {})
        rows = report_data.get("rows", [])

        # --- PDF Setup ---
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4), 
            topMargin=1.0*cm, bottomMargin=1.5*cm,
            leftMargin=1.5*cm, rightMargin=1.5*cm
        )

        styles = getSampleStyleSheet()
        Normal = styles['Normal']
        Bold = ParagraphStyle('Bold', parent=Normal, fontName='Helvetica-Bold', fontSize=10, leading=12)
        
        # Styles for the header and cards
        NameStyle = ParagraphStyle('NameStyle', parent=Bold, fontSize=11)
        DateRangeStyle = ParagraphStyle('DateRange', parent=Bold, alignment=1, fontSize=12)
        PageStyle = ParagraphStyle('PageStyle', parent=Normal, alignment=2, fontSize=10, textColor=colors.grey)
        BoxLabel = ParagraphStyle('BoxLabel', parent=Bold, alignment=1, fontSize=8, leading=9)
        BoxValue = ParagraphStyle('BoxValue', parent=Bold, alignment=1, fontSize=14, leading=16)

        Story = []

        # --- 1. TOP HEADER (Avatar, Date Range, Page) ---
        avatar_img = None
        photo_url = user_info.get("photo_url")
        if photo_url:
            try:
                if photo_url.startswith('/'):
                    photo_url = settings.SITE_URL + photo_url
                resp = requests.get(photo_url, timeout=5)
                if resp.status_code == 200:
                    avatar_img = Image(BytesIO(resp.content), width=0.8*cm, height=0.8*cm)
            except Exception:
                pass

        user_header_content = [avatar_img, Paragraph(user_info.get("full_name", "Staff Member"), NameStyle)] if avatar_img else [Paragraph(user_info.get("full_name", "Staff Member"), NameStyle)]
        date_display = f"{start_date_obj.strftime('%B %d, %Y')} - {end_date_obj.strftime('%B %d, %Y')}"
        
        # Total: 7.5 + 11.7 + 7.5 = 26.7cm (A4 Landscape usable width)
        header_table = Table([[user_header_content, Paragraph(date_display, DateRangeStyle), Paragraph("Page 1/1", PageStyle)]], 
                             colWidths=[7.5*cm, 11.7*cm, 7.5*cm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LINEBELOW', (0,0), (-1,0), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ]))
        Story.append(header_table)
        Story.append(Spacer(1, 0.6*cm))

        # --- 2. SUMMARY BOXES (Colored Row) ---
        def make_box(label, value, bg_color):
            label_text = label.upper().replace(" ", "<br/>")
            if "<br/>" not in label_text: label_text += "<br/>&nbsp;"
            
            p_label = Paragraph(label_text, BoxLabel)
            p_value = Paragraph(f"<b>{value:.2f}</b>", BoxValue)
            
            if bg_color == colors.HexColor("#2196F3"):
                 p_label.textColor = colors.white
                 p_value.textColor = colors.white

            box_table = Table([[p_label], [p_value]], colWidths=[3.7*cm], rowHeights=[0.8*cm, 0.7*cm])
            box_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), bg_color),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (0,0), 'TOP'),
                ('VALIGN', (0,1), (0,1), 'BOTTOM'),
                ('ROUNDEDCORNERS', [6, 6, 6, 6]), 
            ]))
            return box_table

        summary_row = [
            make_box("Work Hours", summary.get('work_hours', 0), colors.HexColor("#E8F5E9")),
            make_box("Paid Breaks", 0.00, colors.HexColor("#EDE7F6")),
            make_box("Paid Absences", 0.00, colors.HexColor("#FFF3E0")),
            make_box("Total Paid", summary.get('work_hours', 0), colors.HexColor("#2196F3")),
            make_box("Regular", summary.get('regular', 0), colors.HexColor("#E3F2FD")),
            make_box("Overtime", summary.get('overtime', 0), colors.HexColor("#E1F5FE")),
            make_box("Unpaid Breaks", 0.00, colors.HexColor("#FBE9E7")),
        ]

        summary_table = Table([summary_row], colWidths=[3.81*cm]*7)
        summary_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        Story.append(summary_table)
        Story.append(Spacer(1, 1*cm))

        # --- 3. ATTENDANCE TABLE (Dates on every row + Last row total) ---
        attendance_data = [[
            Paragraph("<b>Date</b>", Bold),
            Paragraph("<b>Type</b>", Bold),
            Paragraph("<b>Sub job</b>", Bold),
            Paragraph("<b>Clock in</b>", Bold),
            Paragraph("<b>Clock out</b>", Bold),
            Paragraph("<b>Total hours</b>", Bold),
            Paragraph("<b>Daily total</b>", Bold),
        ]]

        total_row_indices = []

        for day in rows:
            # Add session rows
            for session in day['sessions']:
                cin = session['clock_in'].strftime("%H:%M") if session['clock_in'] else "--"
                cout = session['clock_out'].strftime("%H:%M") if session['clock_out'] else "--"
                
                attendance_data.append([
                    Paragraph(day['date_display'], Normal),
                    Paragraph(session['type'], Normal),
                    Paragraph("No sub jobs", Normal),
                    Paragraph(cin, Normal),
                    Paragraph(cout, Normal),
                    Paragraph(f"{session['hours']:.2f}", Normal),
                    "" # No daily total on individual session rows
                ])

            # Add Daily Total Row
            total_row_indices.append(len(attendance_data))
            attendance_data.append([
                "", "", "", "", "", 
                Paragraph("<b>Daily Total:</b>", Bold), 
                Paragraph(f"<b>{day['day_total']:.2f}</b>", Bold)
            ])

        col_widths = [3.8*cm, 3.8*cm, 4.5*cm, 3.2*cm, 3.2*cm, 4.1*cm, 4.1*cm]
        main_table = Table(attendance_data, colWidths=col_widths, repeatRows=1)
        
        main_styles = [
            ('GRID', (0,0), (-1,-1), 0.25, colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (3,0), (-1,-1), 'CENTER'),
            ('ALIGN', (4,0), (-1,-1), 'CENTER'),
            ('ALIGN', (5,0), (-1,-1), 'CENTER'),
            ('ALIGN', (6,0), (-1,-1), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke), # Header background
        ]

        # Apply Light Grey background and Right alignment to Daily Total rows
        for idx in total_row_indices:
            main_styles.append(('BACKGROUND', (0, idx), (-1, idx), colors.whitesmoke))
            main_styles.append(('TOPPADDING', (0, idx), (-1, idx), 10))
            main_styles.append(('BOTTOMPADDING', (0, idx), (-1, idx), 10))

        main_table.setStyle(TableStyle(main_styles))
        Story.append(main_table)

        # --- 4. OUTPUT ---
        doc.build(Story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Attendance_{user_info.get('full_name', 'Report')}_{start_date}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

    except Exception as e:
        traceback.print_exc()
        return HttpResponse(f"Internal Server Error: {str(e)}", status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_detailed_attendance_report(request):
    """
    Endpoint for daily-grouped attendance report.
    """
    user_id = request.query_params.get('user_id')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')

    # 1. Parameter Validation
    if not all([user_id, start_date, end_date]):
        Logs.atuta_logger(f"User {request.user.username} requested report with missing parameters.")
        return Response({
            "status": "error", 
            "message": "Missing required parameters: user_id, start_date, and end_date are required."
        }, status=400)

    # 2. RBAC (Role Based Access Control)
    is_admin = request.user.user_role in ['admin', 'super']
    is_self = str(request.user.user_id) == str(user_id)

    if not (is_admin or is_self):
        Logs.atuta_logger(f"UNAUTHORIZED ACCESS ATTEMPT: {request.user.username} tried to view report for user_id {user_id}")
        return Response({
            "status": "error", 
            "message": "You do not have permission to view this report."
        }, status=403)

    # 3. Data Fetching
    try:
        report_data = AttendanceService.get_detailed_attendance_report(user_id, start_date, end_date)

        if not report_data:
            return Response({
                "status": "error", 
                "message": "Employee record not found."
            }, status=404)

        return Response({
            "status": "success",
            "message": report_data
        })

    except Exception as e:
        Logs.atuta_technical_logger(f"API EXCEPTION in api_get_detailed_attendance_report: {str(e)}")
        return Response({
            "status": "error", 
            "message": "An internal server error occurred while generating the report."
        }, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_attendance_history(request):
    """
    Retrieves attendance records based on date range and optional user filtering.
    QueryParams: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), user_id (optional)
    """
    try:
        # 1. Extract Query Parameters
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        requested_user_id = request.query_params.get("user_id")

        # 2. Permission Logic (RBAC)
        # If the user is NOT an admin/super, they are locked to their own ID
        if request.user.user_role not in ['super', 'admin']:
            target_user_id = str(request.user.user_id)
        else:
            # Admins can filter by a specific user or pass None for all users
            target_user_id = requested_user_id

        # 3. Date Parsing & Validation
        start_date = None
        end_date = None

        try:
            if start_date_str:
                start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if end_date_str:
                end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({
                "status": "error", 
                "message": "invalid_date_format_use_YYYY-MM-DD"
            }, status=400)

        # 4. Call the Service Layer
        result = AttendanceService.get_attendance_history(
            start_date=start_date,
            end_date=end_date,
            user_id=target_user_id
        )

        # 5. Response Mapping
        if result["status"] == "success":
            return Response(result, status=200)
        
        return Response(result, status=400)

    except Exception as e:
        # Technical log for server-side issues
        Logs.atuta_technical_logger(f"api_attendance_history_view_failed", exc_info=e)
        return Response({
            "status": "error",
            "message": "internal_server_error"
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_get_user_attendance_history(request):
    """
    Admin/staff fetches attendance records for any user.
    user_id must be supplied in request.data or query string.
    Optional filters: start_date, end_date
    """
    try:
        # Accept user_id either way — flexible
        user_id = request.data.get("user_id") or request.GET.get("user_id")

        if not user_id:
            return Response(
                {"status": "error", "message": "user_id_required"},
                status=400
            )

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        result = AttendanceService.get_user_attendance_history(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_admin_get_user_attendance_history_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_user_attendance_history(request):
    """
    Authenticated user fetches their own attendance history.
    Optional filters: start_date, end_date
    """
    try:
        start_date = request.GET.get("start_date")  # optional
        end_date = request.GET.get("end_date")      # optional

        user_id = request.user.user_id  # Force logged-in user only

        result = AttendanceService.get_user_attendance_history(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        status_code = 200 if result.get("status") == "success" else 400
        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_user_attendance_history_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_today_user_time_summary(request):
    """
    Fetch today's attendance summary for all users with attendance activity.
    Includes earliest clock-in, latest clock-out, total hours worked,
    user photo URL, clock-in photo URL, and user role.
    """
    try:
        result = AttendanceService.get_today_user_time_summary()

        # Return 200 for success, 400 if something went wrong
        status_code = 200 if result.get("status") == "success" else 400

        return Response(result, status=status_code)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_today_user_time_summary_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_current_session(request):
    """
    Retrieve the user's current active attendance session (clocked in but not clocked out).
    """
    try:
        result = AttendanceService.get_current_session(user=request.user)

        if result["status"] == "error":
            if result["message"] == "no_active_session":
                return Response(result, status=404)  # Not found
            return Response(result, status=400)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_current_session_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_clock_in(request):
    """
    API endpoint for user clock-in. 
    Accepts timestamp, photo_base64, and clockin_type.
    """
    timestamp_str = request.data.get("timestamp")
    photo_base64 = request.data.get("photo_base64") or None
    # Default to "regular" if not provided by the frontend
    clockin_type = request.data.get("clockin_type", "regular") 

    if not timestamp_str:
        return Response(
            {"status": "error", "message": "missing_timestamp"},
            status=400
        )

    # Robust parsing that handles Z suffix and offsets
    try:
        # Using fromisoformat to match modern Python standards
        timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return Response(
            {"status": "error", "message": "invalid_timestamp_format"},
            status=400
        )

    # Call the updated service method
    result = AttendanceService.clock_in(
        user=request.user,
        timestamp=timestamp,
        clockin_type=clockin_type,
        photo_base64=photo_base64
    )

    # Proper HTTP status mapping
    if result["status"] == "success":
        return Response(result, status=201)

    # Logic-based errors
    if result["message"] == "active_session_exists":
        return Response(result, status=409)  # Conflict

    if result["message"] == "user_on_leave":
        return Response(result, status=403)  # Forbidden

    # Validation errors
    if result["message"] in ["invalid_photo_data", "invalid_clockin_type"]:
        return Response(result, status=422)  # Unprocessable Entity

    if result["message"] == "missing_timestamp":
        return Response(result, status=400)  # Bad Request

    # Everything else we treat as server failure
    return Response(result, status=500)

    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_clock_out(request):
    """
    Clock out a user with optional notes.
    Expected payload:
    {
        "timestamp": "2025-12-02T17:00:00",
        "notes": "Leaving early today"  # optional
    }
    """
    try:
        timestamp = request.data.get("timestamp")
        notes = request.data.get("notes")  # optional

        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)
        from django.utils import timezone
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp)

        result = AttendanceService.clock_out(
            user=request.user,
            timestamp=timestamp,
            notes=notes
        )

        if result["status"] == "error":
            if result["message"] == "no_active_session":
                return Response(result, status=409)  # Conflict
            return Response(result, status=400)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_clock_out_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_lunch_in(request):
    """
    Record lunch in.
    """
    try:
        timestamp = request.data.get("timestamp")
        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)

        result = AttendanceService.lunch_in(
            user=request.user,
            timestamp=timestamp
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_lunch_in_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_lunch_out(request):
    """
    Record lunch out.
    """
    try:
        timestamp = request.data.get("timestamp")
        if not timestamp:
            return Response({"status": "error", "message": "missing_timestamp"}, status=400)

        timestamp = datetime.datetime.fromisoformat(timestamp)

        result = AttendanceService.lunch_out(
            user=request.user,
            timestamp=timestamp
        )

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_lunch_out_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_total_hours(request):
    """
    Calculate total hours for the last active session.
    """
    try:
        session = AttendanceSession.objects.filter(user=request.user).last()

        if not session:
            return Response({"status": "error", "message": "no_session"}, status=404)

        result = AttendanceService.calculate_total_hours(session)

        return Response(result, status=200)

    except Exception as e:
        Logs.atuta_technical_logger("api_get_total_hours_failed", exc_info=e)
        return Response({"status": "error", "message": "server_error"}, status=500)
