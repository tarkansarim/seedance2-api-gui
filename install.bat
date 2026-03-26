@echo off
cd /d "%~dp0"
set APP_DIR=%cd%

echo === Seedance 2 API GUI - Installer ===

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: python not found. Install Python 3.10+ first.
    pause
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists.
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q

if not exist output mkdir output

if not exist .env (
    echo MUAPI_API_KEY=your_key_here> .env
    echo.
    echo Created .env file. Edit it with your MuAPI key, or set it in the app's Settings.
)

:: Create Windows shortcut on Desktop
echo Creating desktop shortcut...
set SHORTCUT=%USERPROFILE%\Desktop\Seedance 2.0.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%APP_DIR%\run.bat'; $s.WorkingDirectory = '%APP_DIR%'; $s.IconLocation = '%APP_DIR%\icon.png'; $s.Description = 'Seedance 2.0 Video Generation GUI'; $s.Save()"
if exist "%SHORTCUT%" (
    echo Desktop shortcut created.
) else (
    echo Could not create shortcut. Run manually with: run.bat
)

:: Create Start Menu shortcut
set STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Seedance 2.0.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTMENU%'); $s.TargetPath = '%APP_DIR%\run.bat'; $s.WorkingDirectory = '%APP_DIR%'; $s.IconLocation = '%APP_DIR%\icon.png'; $s.Description = 'Seedance 2.0 Video Generation GUI'; $s.Save()" 2>nul
if exist "%STARTMENU%" echo Start Menu shortcut created.

echo.
echo === Installation complete ===
echo Run with: run.bat or use the desktop shortcut.
pause
