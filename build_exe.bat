@echo off
setlocal
cd /d "%~dp0"

echo [DEBUG] Target Directory: %cd%

set APP_VERSION=%1
if "%APP_VERSION%"=="" set APP_VERSION=1.0.0
:: Strip leading 'v' if present
if "%APP_VERSION:~0,1%"=="v" set APP_VERSION=%APP_VERSION:~1%

:: Check Semantic Versioning (X.Y.Z)
echo %APP_VERSION%| findstr /R "^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo [ERROR] Invalid Version format: %APP_VERSION%. Use X.Y.Z (e.g. 1.0.1)
    pause
    exit /b
)

:: Update setup.py and pyproject.toml
echo [INFO] Bumping version to %APP_VERSION% in setup.py and pyproject.toml...
powershell -Command "(Get-Content setup.py) -replace 'version=\".*\"', 'version=\"%APP_VERSION%\"' | Set-Content setup.py"
powershell -Command "(Get-Content pyproject.toml) -replace 'version = \".*\"', 'version = \"%APP_VERSION%\"' | Set-Content pyproject.toml"

:: Update file_version_info.txt
set "TUPLE_VERSION=%APP_VERSION:.=, %, 0"
powershell -Command "(Get-Content file_version_info.txt) -replace 'filevers=\(.*\)', 'filevers=(%TUPLE_VERSION%)' -replace 'prodvers=\(.*\)', 'prodvers=(%TUPLE_VERSION%)' -replace \"u'FileVersion', u'.*'\", \"u'FileVersion', u'%APP_VERSION%'\" -replace \"u'ProductVersion', u'.*'\", \"u'ProductVersion', u'%APP_VERSION%'\" | Set-Content file_version_info.txt"

set TAILWIND_VERSION=v4.2.4

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

echo [INFO] Building Tailwind CSS...
if not exist "tailwindcss" mkdir tailwindcss
if not exist "tailwindcss\tailwindcss.exe" (
    echo [INFO] Downloading Tailwind CLI...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tailwindlabs/tailwindcss/releases/download/%TAILWIND_VERSION%/tailwindcss-windows-x64.exe' -OutFile 'tailwindcss\tailwindcss.exe'"
)
.\tailwindcss\tailwindcss.exe -i ./static/src/input.css -o ./static/dist/output.css --minify

echo [INFO] Building Standalone EXE (this may take a few minutes)...
rem Note: Ensure there are NO trailing spaces after any of the carets (^) below
python -m PyInstaller --noconfirm --onefile --noconsole --upx-dir=./tools
    --name="Server Monitor" ^
    --icon="icons/win-icon.ico" ^
    --uac-admin ^
    --collect-all pyghmi ^
    --add-data "favicon.ico;." ^
    --add-data "static;static" ^
    --add-data "templates;templates" ^
    --add-data "monitor_core;monitor_core" ^
    --add-data "lib;lib" ^
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