# Build Tailwind
mkdir -p tailwindcss
Invoke-WebRequest -Uri "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-windows-x64.exe" -OutFile "tailwindcss/tailwindcss.exe"
.\tailwindcss\tailwindcss.exe -i ./static/src/input.css -o ./static/dist/output.css --minify

# Build EXE
python -m PyInstaller --noconfirm --onefile --noconsole `
  --upx-dir="$env:UPX_PATH" `
  --name="Server-Monitor" `
  --icon="./icons/win-icon.ico" `
  --uac-admin `
  --collect-all pyghmi `
  --add-data "favicon.ico;." `
  --add-data "static;static" `
  --add-data "templates;templates" `
  --add-data "monitor_core;monitor_core" `
  --add-data "lib;lib" `
  --version-file="file_version_info.txt" `
  --hidden-import=gevent `
  --hidden-import=engineio.async_drivers.gevent `
  --hidden-import=geventwebsocket.gws `
  "server_monitor.py"
