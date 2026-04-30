#!/bin/bash

# --- Configuration ---
RAW_VERSION=${1:-"1.0.0"}
APP_VERSION=${RAW_VERSION#v} # Removes leading 'v' if present
TAILWIND_VERSION=${2:-"v4.2.4"}

# SemVer check
if [[ ! $APP_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[ERROR] Invalid Version format: $APP_VERSION. Use X.Y.Z"
    exit 1
fi

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

# Build Tailwind
mkdir -p tailwindcss
if [ ! -f "tailwindcss/tailwindcss" ]; then
    echo "[INFO] Downloading Tailwind CLI..."
    curl -sL "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-${TW_ARCH}" -o "tailwindcss/tailwindcss"
    chmod +x tailwindcss/tailwindcss
fi
./tailwindcss/tailwindcss -i ./static/src/input.css -o ./static/dist/output.css --minify

# Build Binary
pyinstaller --noconfirm --onefile --name="Server-Monitor" \
  --upx-dir="$UPX_PATH" \
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

# Create .deb
mkdir -p package/usr/local/bin package/usr/share/pixmaps package/usr/share/applications package/DEBIAN
cp dist/Server-Monitor package/usr/local/bin/
cp icons/linux-icon.png package/usr/share/pixmaps/server-monitor.png

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
Maintainer: github-actions
Description: Server Monitor Website" > package/DEBIAN/control

dpkg-deb --build package Server-Monitor.deb
