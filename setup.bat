@echo off
echo Creating virtual environment...
python -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create virtual environment. 
    echo Please ensure Python is installed correctly and you have permissions to write to this folder.
    pause
    exit /b
)

echo Activating...
call .venv\Scripts\activate.bat

echo Installing dependencies from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Setup complete! To activate in the future, run: .\.venv\Scripts\activate
pause