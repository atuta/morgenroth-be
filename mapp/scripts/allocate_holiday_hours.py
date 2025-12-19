#!/usr/bin/env python3

import os
import sys
from pathlib import Path
import django
from datetime import datetime, timedelta
import pytz

# --------------------------------------------------
# Force project root onto PYTHONPATH
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "morgenrothproject.settings")
django.setup()

from django.utils import timezone
from django.db import transaction

from mapp.models import CustomUser, WorkingHoursConfig
from mapp.classes.payroll_service import PayrollService
from mapp.configs.working_hours import WorkingHours
from mapp.classes.logs.logs import Logs


REMARK = "Holiday hours auto allocation"
LUNCH_DEDUCTION_HOURS = 1.0  # subtract 1 hour for lunch by default
KENYA_TZ = pytz.timezone("Africa/Nairobi")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def get_daily_work_hours(user, date):
    """
    Calculate working hours for a user on a specific date using
    WorkingHoursConfig from the DB. Subtracts lunch hours if configured.
    """

    # Convert day name to integer for query
    day_of_week = date.isoweekday()  # Monday=1, Sunday=7
    user_role = user.user_role

    try:
        config = WorkingHoursConfig.objects.get(
            day_of_week=day_of_week,
            user_role=user_role,
            is_active=True
        )
    except WorkingHoursConfig.DoesNotExist:
        return 0.0

    start = datetime.combine(date, config.start_time)
    end = datetime.combine(date, config.end_time)

    total_hours = (end - start).total_seconds() / 3600

    # Subtract lunch if user has lunch configured
    lunch_hours = 0.0
    if getattr(user, "lunch_start", None) and getattr(user, "lunch_end", None):
        lunch_start_hour = user.lunch_start // 100 + (user.lunch_start % 100) / 60
        lunch_end_hour = user.lunch_end // 100 + (user.lunch_end % 100) / 60
        lunch_hours = max(lunch_end_hour - lunch_start_hour, 0.0)

    total_hours = max(total_hours - lunch_hours, 0.0)
    return round(total_hours, 2)


def get_current_utc3_time():
    """Return current time in UTC+3 as string."""
    return datetime.now(pytz.utc).astimezone(KENYA_TZ).strftime("%Y-%m-%d %H:%M:%S")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main():
    today = timezone.now().date()
    month = today.month
    year = today.year

    users = CustomUser.objects.filter(
        is_on_holiday=True,
        is_active=True,
        status="active",
    )

    if not users.exists():
        print("No users on holiday. Nothing to do.")
        return

    print(f"Processing {users.count()} users for {today}")

    success = 0
    skipped = 0
    failed = 0

    for user in users:
        try:
            hours = get_daily_work_hours(user, today)

            if hours <= 0:
                skipped += 1
                print(f"[SKIP] {user.user_id} — no working hours today")
                continue

            with transaction.atomic():
                result = PayrollService.record_hour_correction(
                    user=user,
                    hours=hours,
                    reason=REMARK,
                    corrected_by=None,
                    month=month,
                    year=year,
                )

            if result.get("status") == "success":
                success += 1
                # Log details
                correction_id = result.get("correction_id")
                amount = getattr(result, "amount", "N/A")  # some implementations return amount
                current_time = get_current_utc3_time()
                print(
                    f"[OK] {user.full_name} | hours={hours} | "
                    f"amount={amount} | id={correction_id} | datetime={current_time}"
                )
            else:
                failed += 1
                print(f"[FAIL] {user.user_id}")

        except Exception as e:
            failed += 1
            Logs.atuta_technical_logger(
                f"holiday_hour_allocation_failed_user_{user.user_id}",
                exc_info=e,
            )
            print(f"[ERROR] {user.user_id}")

    print(
        f"Done | Success: {success} | Skipped: {skipped} | Failed: {failed}"
    )


if __name__ == "__main__":
    main()
