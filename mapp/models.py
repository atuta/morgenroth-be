import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
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

def current_month():
    return timezone.now().month

def current_year():
    return timezone.now().year


# -----------------
# CustomUser (keeps your existing structure)
# -----------------
class CustomUserManager(BaseUserManager):
    def create_user(self, username, first_name, last_name, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("Phone number is required")

        if not username:
            raise ValueError("Username is required")

        # Normalize email if provided
        email = extra_fields.get('email')
        if email:
            email = self.normalize_email(email)
            extra_fields['email'] = email

        user = self.model(
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            **extra_fields
        )

        if not user.account:
            user.account = generate_account_id()

        user.set_password(password)
        user.save(using=self._db)
        return user


    def create_superuser(self, username, first_name, last_name, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, first_name, last_name, phone_number, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Login fields
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(max_length=100, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, unique=True)  # REQUIRED FIELD

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    account = models.CharField(max_length=50, unique=True, blank=True, null=True)

    # Roles
    USER_ROLE_CHOICES = [
        ('super', 'Super Admin'),
        ('admin', 'Admin'),
        ('office', 'Office'),
        ('teaching', 'Teaching'),
        ('subordinate', 'Subordinate'),
    ]
    user_role = models.CharField(max_length=20, choices=USER_ROLE_CHOICES, default='subordinate')

    # Staff info
    id_number = models.CharField(max_length=50, null=True, blank=True)
    nssf_number = models.CharField(max_length=50, null=True, blank=True)
    nssf_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monthly NSSF contribution amount"
    )
    shif_sha_number = models.CharField(max_length=50, null=True, blank=True)
    photo = models.ImageField(upload_to='staff_photos/', null=True, blank=True)

    # Work info
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    hourly_rate_currency = models.CharField(max_length=10, default="KES")

    # Lunch policy (24hr format e.g. 1300, 1800)
    lunch_start = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Lunch start time in 24hr format e.g. 1300"
    )
    lunch_end = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Lunch end time in 24hr format e.g. 1400"
    )

    # Attendance
    is_present_today = models.BooleanField(default=False)
    is_on_leave = models.BooleanField(default=False)
    is_on_holiday = models.BooleanField(default=False)

    # Status
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('pending', 'Pending'),
        ('blocked', 'Blocked'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Django permissions
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'phone_number']

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone_number})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        """
        Validate lunch start/end times.
        Stored as 24hr integers e.g. 1300, 1800.
        """
        super().clean()

        for field_name in ("lunch_start", "lunch_end"):
            value = getattr(self, field_name)
            if value is None:
                continue

            if value < 0 or value > 2359:
                raise ValidationError({
                    field_name: "Time must be between 0000 and 2359"
                })

            minutes = value % 100
            if minutes >= 60:
                raise ValidationError({
                    field_name: "Invalid minutes value"
                })

        if self.lunch_start and self.lunch_end:
            if self.lunch_end <= self.lunch_start:
                raise ValidationError(
                    "Lunch end time must be after lunch start time"
                )


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

    # --- Type Identification ---
    CLOCKIN_TYPE_CHOICES = [
        ('regular', 'Regular'),
        ('overtime', 'Overtime'),
    ]
    clockin_type = models.CharField(
        max_length=15, 
        choices=CLOCKIN_TYPE_CHOICES, 
        default='regular'
    )

    # Calculated / misc
    total_hours = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # Photo verification
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
            # Added clockin_type to the index to optimize payroll reporting/filtering
            models.Index(fields=['user', 'date', 'clockin_type']), 
        ]

    def __str__(self):
        return f"{self.user.full_name} | {self.date} | {self.clockin_type} | {self.status}"


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
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE, related_name='advances')

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # new month/year fields
    month = models.PositiveSmallIntegerField(default=current_month)
    year = models.PositiveSmallIntegerField(default=current_year)

    approved_by = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='approved_advances'
    )

    remarks = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-month', '-created_at']
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
            models.Index(fields=['year', 'month']),
        ]

    def __str__(self):
        return f"Advance {self.amount} | {self.user.email} | {self.month}/{self.year}"

# -----------------
# 5. OvertimeAllowance
# -----------------
class OvertimeAllowance(models.Model):
    overtime_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE, related_name="overtimes")

    date = models.DateField(default=timezone.now)  # You didn't have this field explicitly earlier. Needed.
    month = models.PositiveSmallIntegerField(default=current_month)
    year = models.PositiveSmallIntegerField(default=current_year)

    hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    approved_by = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="approved_overtimes"
    )

    remarks = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
            models.Index(fields=['year', 'month']),
        ]

    def __str__(self):
        return f"OT {self.hours}h | {self.amount} | {self.user.email} | {self.month}/{self.year}"
    
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
    
# -----------------
# 17. HourCorrection
# -----------------
class HourCorrection(models.Model):
    correction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="hour_corrections"
    )

    date = models.DateField(default=timezone.now)
    month = models.PositiveSmallIntegerField(default=current_month)
    year = models.PositiveSmallIntegerField(default=current_year)

    # Positive = add hours, Negative = deduct hours
    hours = models.DecimalField(max_digits=5, decimal_places=2)

    # Snapshot of the hourly rate at correction time
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Stored value: hours * hourly_rate
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    corrected_by = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_hour_corrections"
    )

    reason = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
            models.Index(fields=['year', 'month']),
        ]

    def save(self, *args, **kwargs):
        # Freeze hourly rate at time of correction
        if self.hourly_rate is None:
            self.hourly_rate = self.user.hourly_rate

        # Ensure both are Decimal
        hours_decimal = Decimal(str(self.hours))
        hourly_rate_decimal = Decimal(str(self.hourly_rate))

        # Always recalculate amount for consistency
        self.amount = hours_decimal * hourly_rate_decimal

        super().save(*args, **kwargs)

    def __str__(self):
        sign = "+" if self.hours >= 0 else "-"
        return (
            f"Hour Correction {sign}{abs(self.hours)}h | "
            f"{self.user.phone_number} | {self.month}/{self.year}"
        )
    
class HourlyRateSnapshot(models.Model):
    snapshot_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.ForeignKey(
        "mapp.CustomUser",
        on_delete=models.CASCADE,
        related_name="hourly_rate_snapshots"
    )

    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    currency = models.CharField(
        max_length=10,
        default="KES"
    )

    # Period control
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "mapp.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_hourly_rate_snapshots"
    )

    class Meta:
        ordering = ["-effective_from"]
        indexes = [
            models.Index(fields=["user", "effective_from"]),
        ]

    def __str__(self):
        return f"{self.user.full_name} @ {self.hourly_rate} ({self.effective_from})"

class StatutoryDeductionSnapshot(models.Model):
    snapshot_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    deduction = models.ForeignKey(
        "mapp.StatutoryDeduction",
        on_delete=models.CASCADE,
        related_name="snapshots"
    )

    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Period control
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "mapp.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_statutory_deduction_snapshots"
    )

    class Meta:
        ordering = ["-effective_from"]
        indexes = [
            models.Index(fields=["deduction", "effective_from"]),
        ]

    def __str__(self):
        return (
            f"{self.deduction.name} | "
            f"{self.percentage}% | "
            f"{self.effective_from}"
        )

class WorkingHoursConfig(models.Model):
    class Days(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'
        SATURDAY = 6, 'Saturday'
        SUNDAY = 7, 'Sunday'

    USER_ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('office', 'Office'),
        ('teaching', 'Teaching'),
        ('subordinate', 'Subordinate'),
    ]

    day_of_week = models.PositiveSmallIntegerField(choices=Days.choices)

    user_role = models.CharField(
        max_length=20,
        choices=USER_ROLE_CHOICES,
    )

    start_time = models.TimeField()
    end_time = models.TimeField()

    timezone = models.CharField(
        max_length=100,
        default='Africa/Nairobi'
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('day_of_week', 'user_role', 'timezone')
        ordering = ['day_of_week']

    def __str__(self):
        return (
            f"{self.get_day_of_week_display()} | "
            f"{self.get_user_role_display()} | "
            f"{self.start_time} - {self.end_time}"
        )

    
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
    
class OrganizationDetail(models.Model):
    # Autogenerated and compulsory
    org_uuid = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    
    # Compulsory
    name = models.CharField(
        max_length=255, 
        verbose_name="Name of Organization"
    )
    
    # Optional fields (null=True, blank=True)
    logo = models.ImageField(
        upload_to='org_logos/', 
        null=True, 
        blank=True
    )
    
    physical_address = models.TextField(null=True, blank=True)
    postal_address = models.CharField(max_length=255, null=True, blank=True)
    telephone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

    def __str__(self):
        return self.name
