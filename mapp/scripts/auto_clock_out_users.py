#!/usr/bin/env python3

import os
import sys
from pathlib import Path
import django
from datetime import datetime
import pytz

# --------------------------------------------------
# Force project root onto PYTHONPATH
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "morgenrothproject.settings")
django.setup()

from django.utils import timezone

from mapp.classes.attendance_service import AttendanceService
from mapp.classes.logs.logs import Logs


KENYA_TZ = pytz.timezone("Africa/Nairobi")


def get_current_utc3_time():
    return datetime.now(pytz.utc).astimezone(KENYA_TZ).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    start_time = get_current_utc3_time()
    Logs.atuta_logger(f"Auto clock-out job started at {start_time}")
    print(f"Auto clock-out job started at {start_time}")

    try:
        AttendanceService.auto_clock_out_users_at_day_end()

        end_time = get_current_utc3_time()
        Logs.atuta_logger(f"Auto clock-out job finished at {end_time}")
        print(f"Auto clock-out job finished at {end_time}")

    except Exception as e:
        Logs.atuta_technical_logger(
            "auto_clock_out_cron_failed",
            exc_info=e
        )
        print("Auto clock-out job failed")


if __name__ == "__main__":
    main()
