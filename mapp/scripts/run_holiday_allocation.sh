#!/usr/bin/env bash

set -e  # exit immediately on error

# --------------------------------------------------
# Paths (CHANGE ONLY IF YOUR STRUCTURE CHANGES)
# --------------------------------------------------
PROJECT_ROOT="/Users/isaac/python_projects/morgenroth/morgenrothproject"
VENV_PATH="/Users/isaac/python_projects/morgenroth/morgenroth_env"
SCRIPT_PATH="$PROJECT_ROOT/mapp/scripts/allocate_holiday_hours.py"

# --------------------------------------------------
# Activate virtualenv
# --------------------------------------------------
source "$VENV_PATH/bin/activate"

# --------------------------------------------------
# Move to project root (important for imports)
# --------------------------------------------------
cd "$PROJECT_ROOT"

# --------------------------------------------------
# Run script
# --------------------------------------------------
python "$SCRIPT_PATH"

# --------------------------------------------------
# Optional: deactivate venv
# --------------------------------------------------
deactivate
