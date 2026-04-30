#!/bin/bash
# Build Tailwind
mkdir -p tailwindcss
curl -sL "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-linux-x64" -o "tailwindcss/tailwindcss"
chmod +x tailwindcss/tailwindcss
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
Version: 1.0.0
Architecture: amd64
Maintainer: github-actions
Description: Server Monitor Website" > package/DEBIAN/control

dpkg-deb --build package Server-Monitor.deb
