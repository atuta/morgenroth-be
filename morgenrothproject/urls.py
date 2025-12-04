from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from mapp.views import (
    admin_notice_view,
    attendance_view,
    advance_view,
    deduction_view,
    overtime_view,
    payroll_view,
    rate_view,
    sms_view,
    support_ticket_view,
    system_message_view,
    system_setting_view,
    user_manual_view,
    user_view,
    verification_view
)

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', user_view.blank, name='blank'),

    # Admin notice endpoints
    path('api/create-admin-notice/', admin_notice_view.api_create_admin_notice, name='create_admin_notice'),
    path('api/get-admin-notices/', admin_notice_view.api_get_admin_notices, name='get_admin_notices'),
    path('api/update-admin-notice/', admin_notice_view.api_update_admin_notice, name='update_admin_notice'),
    path('api/delete-admin-notice/', admin_notice_view.api_delete_admin_notice, name='delete_admin_notice'),


    # User endpoints
    path('api/add-user/', user_view.api_add_user, name='add_user'),
    path('api/upload-user-photo/', user_view.upload_user_photo, name='upload_user_photo'),
    path('api/update-user-fields/', user_view.api_update_user_fields, name='update_user_fields'),
    path('api/get-logged-in-user-details/', user_view.api_get_logged_in_user_details, name='get_logged_in_user_details'),
    path('api/get-user-details/', user_view.api_get_user_details, name='get_user_details'),
    path('api/get-non-admin-users/', user_view.api_get_non_admin_users, name='get_non_admin_users'),
    path('api/change-password/', user_view.api_change_password, name='change_password'),
    path('api/top-up-subscription/', user_view.api_top_up_subscription, name='top_up_subscription'),
    path('api/user-full-name/', user_view.api_get_full_name, name='user_full_name'),
    path('api/user-has-permission/', user_view.api_has_permission, name='user_has_permission'),
    path('api/user-has-module-permission/', user_view.api_has_module_permission, name='user_has_module_permission'),
    path('api/login/', user_view.api_login, name='user_login'),

    # Attendance endpoints
    path('api/clock-in/', attendance_view.api_clock_in, name='clock_in'),
    path('api/clock-out/', attendance_view.api_clock_out, name='clock_out'),
    path('api/lunch-in/', attendance_view.api_lunch_in, name='lunch_in'),
    path('api/lunch-out/', attendance_view.api_lunch_out, name='lunch_out'),
    path('api/total-hours/', attendance_view.api_get_total_hours, name='total_hours'),
    path('api/get-today-user-time-summary/', attendance_view.api_get_today_user_time_summary, name='get_today_user_time_summary'),
    path('api/attendance/current-session/', attendance_view.api_get_current_session, name='current_session'),


    # Advance endpoints
    path('api/advance/get-by-month/', advance_view.api_get_user_advances_by_month, name='user_get_advances_by_month'),
    path('api/advance/get-all/', advance_view.api_get_all_user_advances, name='user_get_all_advances'),
    path('api/admin/advance/create/', advance_view.api_admin_create_advance, name='admin_create_advance'),
    path('api/admin/advance/get-by-month/', advance_view.api_admin_get_user_advances_by_month, name='admin_get_advances_by_month'),
    path('api/admin/advance/get-all/', advance_view.api_admin_get_all_user_advances, name='admin_get_all_advances'),

    # Deduction endpoints
    path('api/set-deduction/', deduction_view.api_set_deduction, name='set_deduction'),
    path('api/get-deduction/', deduction_view.api_get_deduction, name='get_deduction'),

    # Overtime endpoints
    path('api/overtime/record/', overtime_view.api_admin_record_overtime, name='admin_record_overtime'),
    path('api/overtime/get-by-month/', overtime_view.api_get_user_overtime_by_month, name='user_get_overtime_by_month'),
    path('api/overtime/get-all/', overtime_view.api_get_all_user_overtime, name='user_get_all_overtime'),
    path('api/admin/overtime/get-by-month/', overtime_view.api_admin_get_user_overtime_by_month, name='admin_get_overtime_by_month'),
    path('api/admin/overtime/get-all/', overtime_view.api_admin_get_all_user_overtime, name='admin_get_all_overtime'),

    # Payroll endpoints
    path('api/generate-monthly-salary/', payroll_view.api_generate_monthly_salary, name='generate_monthly_salary'),
    path('api/calculate-net-salary/', payroll_view.api_calculate_net_salary, name='calculate_net_salary'),
    path('api/generate-salary-slip/', payroll_view.api_generate_salary_slip, name='generate_salary_slip'),
    path('api/get-salary-slip/', payroll_view.api_get_salary_slip, name='get_salary_slip'),
    path('api/generate-payment-report/', payroll_view.api_generate_payment_report, name='generate_payment_report'),
    path('api/get-payment-summary/', payroll_view.api_get_payment_summary, name='get_payment_summary'),

    # Rate endpoints
    path('api/set-rate/', rate_view.api_set_rate, name='set_rate'),
    path('api/get-rate/', rate_view.api_get_rate, name='get_rate'),

    # SMS endpoints
    path('api/send-sms/', sms_view.api_send_sms, name='send_sms'),
    path('api/get-sms-log/', sms_view.api_get_sms_log, name='get_sms_log'),

    # Support ticket endpoints
    path('api/create-support-ticket/', support_ticket_view.api_create_support_ticket, name='create_ticket'),
    path('api/update-support-ticket/', support_ticket_view.api_update_support_ticket, name='update_ticket'),
    path('api/get-user-tickets/', support_ticket_view.api_get_user_tickets, name='get_user_tickets'),

    # System message endpoints
    path('api/create-system-message/', system_message_view.api_create_system_message, name='create_system_message'),
    path('api/mark-system-message-read/', system_message_view.api_mark_system_message_as_read, name='mark_system_message_read'),

    # System setting endpoints
    path('api/get-working-hours/', system_setting_view.api_get_working_hours, name='get_working_hours'),
    path('api/set-working-hours/', system_setting_view.api_set_working_hours, name='set_working_hours'),
    path('api/set-system-setting/', system_setting_view.api_set_system_setting, name='set_system_setting'),
    path('api/get-system-setting/', system_setting_view.api_get_system_setting, name='get_system_setting'),

    # User manual endpoints
    path('api/add-user-manual/', user_manual_view.api_add_user_manual, name='add_user_manual'),
    path('api/get-user-manual/', user_manual_view.api_get_user_manual, name='get_user_manual'),

    # Verification endpoints
    path('api/record-verification/', verification_view.api_record_verification, name='record_verification'),
    path('api/get-verification-history/', verification_view.api_get_verification_history, name='get_verification_history'),
]

# JWT auth endpoints
urlpatterns += [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
