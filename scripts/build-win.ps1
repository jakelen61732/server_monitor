# Configuration
param(
    [string]$Version = "1.0.0",
    [string]$TailwindVersion = "v4.2.4"
)

$Version = $Version -replace '^v', '' # Removes leading 'v' if present

# SemVer check
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Error "[ERROR] Invalid Version format: $Version. Use X.Y.Z"
    exit 1
}

# Update setup.py and pyproject.toml
(Get-Content setup.py) -replace 'version=".*"', "version=""$Version""" | Set-Content setup.py
(Get-Content pyproject.toml) -replace 'version = ".*"', "version = ""$Version""" | Set-Content pyproject.toml

# Update file_version_info.txt
$TupleVersion = $Version.Replace('.', ', ') + ", 0"
(Get-Content file_version_info.txt) `
    -replace 'filevers=\(.*\)', "filevers=($TupleVersion)" `
    -replace 'prodvers=\(.*\)', "prodvers=($TupleVersion)" `
    -replace "u'FileVersion', u'.*'", "u'FileVersion', u'$Version'" `
    -replace "u'ProductVersion', u'.*'", "u'ProductVersion', u'$Version'" | Set-Content file_version_info.txt

# Build Tailwind
mkdir -p tailwindcss
if (!(Test-Path "tailwindcss/tailwindcss.exe")) {
    Invoke-WebRequest -Uri "https://github.com/tailwindlabs/tailwindcss/releases/download/$TailwindVersion/tailwindcss-windows-x64.exe" -OutFile "tailwindcss/tailwindcss.exe"
}
.\tailwindcss\tailwindcss.exe -i ./static/src/input.css -o ./static/dist/output.css --minify

# Build EXE
python -m PyInstaller --noconfirm --onefile --noconsole `
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
