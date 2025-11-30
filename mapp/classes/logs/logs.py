import os
import traceback
from datetime import datetime, timedelta
from mapp.models import ErrorLog
class Logs:
    """
    Logging utility: logs to file and to DB (ErrorLog).
    Text files still stored by hour; DB stores full history for reporting.
    """

    LOG_DIR = "./log_files"

    @staticmethod
    def _save_to_db(text):
        """Persist log text to DB. Date fields auto-populated by model."""
        try:
            ErrorLog.objects.create(log_text=str(text))
        except Exception as e:
            # Fallback console output if DB fails — do NOT crash the task
            print(f"[DB-LOGGING-ERROR] {e}")

    @staticmethod
    def atuta_technical_logger(text, exc_info=None):
        """Log technical messages & exceptions."""
        utc_plus_3 = datetime.utcnow() + timedelta(hours=3)
        file_name = utc_plus_3.strftime("%Y-%m-%d-%H") + "-tech.txt"
        file_path = os.path.join(Logs.LOG_DIR, file_name)

        try:
            os.makedirs(Logs.LOG_DIR, exist_ok=True)

            with open(file_path, 'a') as file:
                file.write(str(text) + '\n\n')

                if exc_info:
                    filename, line, func, _ = traceback.extract_tb(exc_info.__traceback__)[-1]
                    error_details = (
                        f"Error in file: {filename}, line: {line}, "
                        f"in {func} - {str(exc_info)}"
                    )
                    file.write(error_details + '\n')

            # Save to DB too
            Logs._save_to_db(f"TECH | {text}")

            return {"message": "Log entry added successfully."}

        except Exception as e:
            return {"error": f"Logging error occurred: {str(e)}"}

    @staticmethod
    def atuta_logger(text, exc_info=None):
        """Log general system messages."""
        utc_plus_3 = datetime.utcnow() + timedelta(hours=3)
        file_name = utc_plus_3.strftime("%Y-%m-%d-%H") + ".txt"
        file_path = os.path.join(Logs.LOG_DIR, file_name)

        try:
            os.makedirs(Logs.LOG_DIR, exist_ok=True)

            with open(file_path, 'a') as file:
                file.write(str(text) + '\n\n')

                if exc_info:
                    filename, line, func, _ = traceback.extract_tb(exc_info.__traceback__)[-1]
                    error_details = (
                        f"Error in file: {filename}, line: {line}, "
                        f"in {func} - {str(exc_info)}"
                    )
                    file.write(error_details + '\n')

            # Save to DB too
            Logs._save_to_db(text)

            return {"message": "Log entry added successfully."}

        except Exception as e:
            return {"error": f"Logging error occurred: {str(e)}"}
