#!/bin/bash

# --- Configuration ---
RAW_VERSION=${1:-"1.0.0"}
APP_VERSION=${RAW_VERSION#v} # Removes leading 'v' if present
TAILWIND_VERSION="v4.2.4"

# SemVer check
if [[ ! $APP_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[ERROR] Invalid Version format: $APP_VERSION. Use X.Y.Z"
    exit 1
fi

# Ensure we are in the project root
cd "$(dirname "$0")"

# Update project metadata files
echo "[INFO] Bumping version to $APP_VERSION in setup.py and pyproject.toml..."
sed -i "s/version=\".*\"/version=\"$APP_VERSION\"/" setup.py
sed -i "s/version = \".*\"/version = \"$APP_VERSION\"/" pyproject.toml

# Detect Architecture for Tailwind and DEB package
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
case $ARCH in
    amd64) TW_ARCH="x64" ;;
    arm64) TW_ARCH="arm64" ;;
    armhf) TW_ARCH="armv7" ;;
    i386)  TW_ARCH="x86" ;;
    *)     TW_ARCH="x64" ;; # Default to x64
esac
# ---------------------

echo "[INFO] Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo "[ERROR] Virtual environment (.venv) not found."
    echo "Please run ./setup.sh first."
    exit 1
fi

echo "[INFO] Activating virtual environment..."
source .venv/bin/activate

echo "[INFO] Verifying PyInstaller installation..."
python3 -m PyInstaller --version >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[INFO] PyInstaller not found. Installing..."
    pip install pyinstaller
fi

echo "[INFO] Building Tailwind CSS..."
mkdir -p tailwindcss
if [ ! -f "tailwindcss/tailwindcss" ]; then
    echo "[INFO] Downloading Tailwind CLI..."
    curl -sL "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-${TW_ARCH}" -o "tailwindcss/tailwindcss"
    chmod +x tailwindcss/tailwindcss
fi
./tailwindcss/tailwindcss -i ./static/src/input.css -o ./static/dist/output.css --minify

echo "[INFO] Building Standalone Binary..."
python3 -m PyInstaller --noconfirm --onefile --name="Server-Monitor" \
    --collect-all pyghmi \
    --add-data "favicon.ico:." \
    --add-data "static:static" \
    --add-data "templates:templates" \
    --add-data "monitor_core:monitor_core" \
    --add-data "lib:lib" \
    --hidden-import=gevent \
    --hidden-import=engineio.async_drivers.gevent \
    --hidden-import=geventwebsocket.gws \
    "server_monitor.py"

if [ $? -ne 0 ]; then
    echo "[ERROR] Build failed during PyInstaller phase."
    exit 1
fi

echo "[INFO] Packaging for Debian..."
mkdir -p package/usr/local/bin package/usr/share/pixmaps package/usr/share/applications package/DEBIAN
cp dist/Server-Monitor package/usr/local/bin/

if [ -f "icons/linux-icon.png" ]; then
    cp icons/linux-icon.png package/usr/share/pixmaps/server-monitor.png
fi

echo "[Desktop Entry]
Name=Server Monitor
Exec=/usr/local/bin/Server-Monitor
Icon=server-monitor
Type=Application
Categories=Utility;
Terminal=false" > package/usr/share/applications/server-monitor.desktop

echo "Package: server-monitor
Version: $APP_VERSION
Architecture: $ARCH
Maintainer: KJAYDev
Description: Professional cross-platform server monitoring tool" > package/DEBIAN/control

dpkg-deb --build package Server-Monitor.deb
echo "[SUCCESS] Build complete! Package: Server-Monitor.deb"