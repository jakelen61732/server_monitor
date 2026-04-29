@echo off
echo Detected OS: Windows

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    pause
    exit /b
)

:: Create Virtual Environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Install Dependencies
echo Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Setup complete. Run 'python server_monitor.py' to start the monitor.
pause