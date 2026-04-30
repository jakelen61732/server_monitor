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

:: Download Build Tools (Tailwind and UPX)
set TAILWIND_VERSION=v4.2.4
set UPX_VERSION=5.1.1

echo [INFO] Checking for required build tools (Tailwind CLI and UPX)...
if not exist "tailwindcss" mkdir tailwindcss
if not exist "tailwindcss\tailwindcss.exe" (
    echo [INFO] Downloading Tailwind CLI version %TAILWIND_VERSION%...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tailwindlabs/tailwindcss/releases/download/%TAILWIND_VERSION%/tailwindcss-windows-x64.exe' -OutFile 'tailwindcss\tailwindcss.exe'"
) else (
    echo [INFO] Tailwind CLI already exists. Skipping download.
)

if not exist "tools" mkdir tools
if not exist "tools\upx.exe" (
    echo [INFO] Downloading UPX version %UPX_VERSION%...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v%UPX_VERSION%/upx-%UPX_VERSION%-win64.zip' -OutFile 'tools\upx.zip'"
    powershell -Command "Expand-Archive -Path 'tools\upx.zip' -DestinationPath 'tools' -Force"
    copy /y "tools\upx-%UPX_VERSION%-win64\upx.exe" "tools\upx.exe"
    rmdir /s /q "tools\upx-%UPX_VERSION%-win64"
    del "tools\upx.zip"
) else (
    echo [INFO] UPX already exists. Skipping download.
)

echo Setup complete. Run 'python server_monitor.py' to start the monitor.
pause