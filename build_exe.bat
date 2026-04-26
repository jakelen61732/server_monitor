@echo off
setlocal
cd /d "%~dp0"

echo [DEBUG] Target Directory: %cd%

if not exist ".venv" (
    echo [ERROR] Virtual environment (.venv) not found.
    echo Please ensure you have run setup.bat successfully before building.
    pause
    exit /b
)

if not exist "favicon-64x64.ico" (
    echo [ERROR] favicon-64x64.ico not found in the current directory.
    echo Please place an icon file named 'favicon-64x64.ico' in this folder before building.
    pause
    exit /b
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate

echo [INFO] Verifying PyInstaller installation...
python -m PyInstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] PyInstaller not found in .venv. Installing now...
    pip install pyinstaller
)

echo [INFO] Building Standalone EXE (this may take a few minutes)...
python -m PyInstaller --noconfirm --onefile --noconsole --upx-dir=./upx ^
    --name="Server Monitor" ^
    --icon="favicon-64x64.ico" ^
    --add-data "favicon.ico;." ^
    --add-data "static;static" ^
    --version-file="file_version_info.txt" ^
    --hidden-import=gevent ^
    --hidden-import=engineio.async_drivers.gevent ^
    --hidden-import=geventwebsocket.gws ^
    --exclude-module=tkinter ^
    --exclude-module=tcl ^
    --exclude-module=tk ^
    --exclude-module=idlelib ^
    --exclude-module=unittest ^
    "server_monitor.py"

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller encountered an error. Build failed.
    pause
    exit /b
)

echo [INFO] Signing the executable...
rem Replace the placeholders below with your actual certificate path and password.
rem The /tr and /td flags ensure the signature remains valid even after the certificate expires.
rem "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" sign /f "path\to\KJAYDev_cert.pfx" /p "YourPassword" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\Server Monitor.exe"
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Signing failed. The executable will still work but will show as 'Unknown Publisher'.
)

echo [SUCCESS] Build complete! Your app is in the 'dist' folder.
pause