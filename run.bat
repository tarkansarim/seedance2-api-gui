@echo off
cd /d "%~dp0"
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
python seedance_ui.py
pause
