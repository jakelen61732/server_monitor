#!/bin/bash

# Detect OS/Environment
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME=$NAME
    OS_ID=$ID
elif [ -n "$TERMUX_VERSION" ]; then
    OS_NAME="Android (Termux)"
else
    OS_NAME=$(uname -s)
fi

echo "Detected System: $OS_NAME"

# Install System Dependencies for GUI (pywebview Linux requirements)
if [[ "$OS_NAME" == *"Ubuntu"* ]] || [[ "$OS_NAME" == *"Debian"* ]] || [[ "$OS_NAME" == *"Kali"* ]]; then
    echo "Installing system dependencies for Linux GUI..."
    sudo apt-get update
    sudo apt-get install -y python3-pip python3-venv \
        python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0
elif [[ "$OS_ID" == "fedora" ]] || [[ "$OS_ID" == "centos" ]] || [[ "$OS_ID" == "rhel" ]]; then
    echo "Installing system dependencies for RPM-based GUI..."
    sudo dnf install -y python3-pip python3-virtualenv \
        python3-gobject gtk3 webkit2gtk3
elif [[ "$OS_NAME" == "Android (Termux)" ]]; then
    echo "Installing build tools for Termux..."
    pkg update
    pkg install -y python clang make
fi

# Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete. Run 'source .venv/bin/activate && python3 server_monitor.py' to start."