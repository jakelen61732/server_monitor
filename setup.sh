#!/bin/bash

echo "[INFO] Detecting Linux distribution..."
if [ -f /etc/debian_version ]; then
    echo "[INFO] Installing system dependencies for GUI support..."
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip libwebkit2gtk-4.0-3 python3-gi
fi

echo "[INFO] Creating virtual environment..."
python3 -m venv .venv

echo "[INFO] Activating virtual environment..."
source .venv/bin/activate

echo "[INFO] Upgrading pip..."
pip install --upgrade pip

echo "[INFO] Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "[SUCCESS] Setup complete! To run the monitor, use:"
echo "source .venv/bin/activate && python3 server_monitor.py"