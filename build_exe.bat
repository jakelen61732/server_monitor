@echo off
setlocal
cd /d "%~dp0"

echo [DEBUG] Target Directory: %cd%

rem FIX 1: Removed the trailing backslash inside the quotes
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
call .venv\Scripts\activate.bat

echo [INFO] Verifying PyInstaller installation...
python -m PyInstaller --version >nul 2>&1
rem FIX 2: Ensured 'if errorlevel 1 (' is all on one single line
if errorlevel 1 (
    echo [INFO] PyInstaller not found in .venv. Installing now...
    pip install pyinstaller
)

echo [INFO] Building Standalone EXE (this may take a few minutes)...
rem Note: Ensure there are NO trailing spaces after any of the carets (^) below
python -m PyInstaller --noconfirm --onefile --noconsole --upx-dir=./upx ^
    --name="Server Monitor" ^
    --icon="favicon-64x64.ico" ^
    --add-data "favicon.ico;." ^
    --add-data "static;static" ^
    --add-data "templates;templates" ^
    --add-data "monitor_core;monitor_core" ^
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

if errorlevel 1 (
    echo [ERROR] PyInstaller encountered an error. Build failed.
    pause
    exit /b
)

echo [INFO] Signing the executable...
rem Replace the placeholders below with your actual certificate path and password[cite: 4].
rem The /tr and /td flags ensure the signature remains valid even after the certificate expires[cite: 4].
rem "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" sign /f "path\to\KJAYDev_cert.pfx" /p "YourPassword" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\Server Monitor.exe" [cite: 5]
if errorlevel 1 (
    echo [WARNING] Signing failed. The executable will still work but will show as 'Unknown Publisher'.
)

echo [SUCCESS] Build complete!
Your app is in the 'dist' folder[cite: 6].
pause