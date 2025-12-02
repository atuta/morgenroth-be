import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# -----------------
# Utility / small helpers
# -----------------
def generate_account_id():
    import string, random
    characters = ''.join([c for c in string.ascii_letters + string.digits if c not in '10oil'])
    return ''.join(random.choice(characters) for _ in range(5))


# -----------------
# CustomUser (keeps your existing structure)
# -----------------
class CustomUserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, first_name=first_name, last_name=last_name, **extra_fields)
        if not user.account:
            user.account = generate_account_id()
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, first_name, last_name, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """User model for the Clock-In System"""
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=100)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    account = models.CharField(max_length=50, unique=True, blank=True, null=True)

    # Role
    USER_ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('subordinate', 'Subordinate Staff'),
    ]
    user_role = models.CharField(max_length=20, choices=USER_ROLE_CHOICES, default='staff')

    # Staff info
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    id_number = models.CharField(max_length=50, blank=True, null=True)
    nssf_number = models.CharField(max_length=50, blank=True, null=True)
    shif_sha_number = models.CharField(max_length=50, blank=True, null=True)
    photo = models.ImageField(upload_to='staff_photos/', blank=True, null=True)

    # Hourly rate info
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    hourly_rate_currency = models.CharField(max_length=10, default="KES")

    # Attendance flags
    is_present_today = models.BooleanField(default=False)
    is_on_leave = models.BooleanField(default=False)

    # Account status
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('pending', 'Pending'),
        ('blocked', 'Blocked'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Django required flags
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # Django login settings
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


# -----------------
# 2. AttendanceSession
# -----------------
class AttendanceSession(models.Model):
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='attendance_sessions')

    # Date / times
    date = models.DateField(default=timezone.now)
    clock_in_time = models.DateTimeField(blank=True, null=True)
    lunch_in = models.DateTimeField(blank=True, null=True)
    lunch_out = models.DateTimeField(blank=True, null=True)
    clock_out_time = models.DateTimeField(blank=True, null=True)

    # Calculated / misc
    total_hours = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)  # hours as decimal
    notes = models.TextField(blank=True, null=True)

    # **New field for photo verification**
    clock_in_photo = models.ImageField(upload_to='attendance_photos/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
        ]

    def __str__(self):
        return f"{self.user.full_name} | {self.date} | {self.status}"


# -----------------
# 3. VerificationLog
# -----------------
class VerificationLog(models.Model):
    verification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='verifications')
    timestamp = models.DateTimeField(auto_now_add=True)

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('missed', 'Missed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # Image field for storing uploaded verification photos
    photo = models.ImageField(upload_to='verification_photos/', blank=True, null=True)
    
    # Optional reason for failed or missed verification
    reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user.full_name} | {self.timestamp} | {self.status}"


# -----------------
# 4. AdvancePayment
# -----------------
class AdvancePayment(models.Model):
    advance_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='advances')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    month = models.PositiveSmallIntegerField()  # 1-12
    year = models.PositiveIntegerField()
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='approved_advances')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-month', '-created_at']
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
        ]

    def __str__(self):
        return f"Advance {self.amount} | {self.user.email} | {self.month}/{self.year}"


# -----------------
# 5. OvertimeAllowance
# -----------------
class OvertimeAllowance(models.Model):
    overtime_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='overtimes')
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='approved_overtimes')
    approved_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
        ]

    def __str__(self):
        return f"OT {self.hours}h | {self.user.email} | {self.date} | approved={self.approved_flag}"


# -----------------
# 6. SalaryRecord
# -----------------
class SalaryRecord(models.Model):
    salary_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='salary_records')

    base_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    advances_deducted = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    month = models.PositiveSmallIntegerField()  # 1-12
    year = models.PositiveIntegerField()

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'month', 'year')
        ordering = ['-year', '-month']
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
        ]

    def __str__(self):
        return f"Salary {self.user.email} | {self.month}/{self.year} | net={self.net_pay}"


# -----------------
# 7. SalarySlip
# -----------------
class SalarySlip(models.Model):
    slip_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='salary_slips')
    file_path = models.FileField(upload_to='salary_slips/')
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Slip {self.user.email} | {self.generated_at.date()}"


# -----------------
# 8. PaymentReport
# -----------------
class PaymentReport(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.PositiveSmallIntegerField()  # 1-12
    year = models.PositiveIntegerField()
    total_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_advances = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    balances = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    file_path = models.FileField(upload_to='payment_reports/', blank=True, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('month', 'year')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"PaymentReport | {self.month}/{self.year} | paid={self.total_paid}"


# -----------------
# 9. RateSetting
# -----------------
class RateSetting(models.Model):
    setting_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_role = models.CharField(max_length=50)  # e.g., 'teacher', 'worker', 'staff'
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    overtime_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.5'))
    advance_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('user_role',)
        ordering = ['user_role']

    def __str__(self):
        return f"Rate {self.user_role} | rate={self.hourly_rate} | ot_x={self.overtime_multiplier}"


# -----------------
# 10. StatutoryDeduction
# -----------------
class StatutoryDeduction(models.Model):
    deduction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))  # e.g., 5.00 => 5%

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} | {self.percentage}%"


# -----------------
# 11. SystemSettings
# -----------------
class SystemSettings(models.Model):
    key = models.CharField(max_length=200, unique=True)
    value = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return f"{self.key}"


# -----------------
# 12. SMSLog
# -----------------
class SMSLog(models.Model):
    sms_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sms_logs')
    message = models.TextField()
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('delivered', 'Delivered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    timestamp = models.DateTimeField(auto_now_add=True)
    provider_response = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['recipient', 'timestamp']),
        ]

    def __str__(self):
        return f"SMS | {self.recipient.email} | {self.status} | {self.timestamp}"


# -----------------
# 13. AdminNotice
# -----------------
class AdminNotice(models.Model):
    notice_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=250)
    content = models.TextField()
    recipients = models.ManyToManyField(CustomUser, blank=True, related_name='admin_notices')  # empty => all staff
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notice | {self.title} | active={self.is_active}"


# -----------------
# 14. SystemMessage
# -----------------
class SystemMessage(models.Model):
    message_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='system_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_flag = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'created_at']),
        ]

    def __str__(self):
        return f"SysMsg | {self.recipient.email} | read={self.read_flag}"


# -----------------
# 15. SupportTicket
# -----------------
class SupportTicket(models.Model):
    ticket_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=250)
    description = models.TextField()
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Ticket {self.ticket_id} | {self.subject} | {self.status}"


# -----------------
# 16. UserManual
# -----------------
class UserManual(models.Model):
    manual_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=250)
    file_path = models.FileField(upload_to='user_manuals/', blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='uploaded_manuals')

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Manual | {self.title}"
    
class WorkingHoursConfig(models.Model):
    class Days(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'
        SATURDAY = 6, 'Saturday'
        SUNDAY = 7, 'Sunday'

    day_of_week = models.PositiveSmallIntegerField(choices=Days.choices)

    start_time = models.TimeField()
    end_time = models.TimeField()

    # timezone for that config rule
    timezone = models.CharField(
        max_length=100,
        default='Africa/Nairobi'
    )

    # optional feature: allow disabling a day
    is_active = models.BooleanField(default=True)

    # audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('day_of_week', 'timezone')
        ordering = ['day_of_week']

    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.start_time} - {self.end_time}"

    
class ErrorLog(models.Model):
    # Raw log text as received
    log_text = models.TextField()

    # Time metadata
    timestamp = models.DateTimeField(auto_now_add=True)

    # Date breakdown (auto-filled for reporting)
    year = models.PositiveIntegerField(editable=False)
    month = models.PositiveIntegerField(editable=False)
    week = models.PositiveIntegerField(editable=False)
    day = models.PositiveIntegerField(editable=False)
    hour = models.PositiveIntegerField(editable=False)  # 24-hour format

    class Meta:
        indexes = [
            models.Index(fields=["year", "month"]),
            models.Index(fields=["year", "week"]),
            models.Index(fields=["year", "day"]),
            models.Index(fields=["year", "hour"]),  # Added hour index for fast hourly data analysis
        ]
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        # Auto populate date fields if not already set
        if not self.year or not self.month or not self.week or not self.day or not self.hour:
            ts = now()
            self.year = ts.year
            self.month = ts.month
            self.week = ts.isocalendar().week
            self.day = ts.day
            self.hour = ts.hour  # 24-hr format

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.timestamp} | Log"
