# Server Monitor Dashboard

A professional, cross-platform server monitoring tool with a real-time web dashboard and a standalone desktop GUI. Built with Python, Flask-SocketIO, and Tailwind CSS.

## 🚀 Features

- **Real-Time Monitoring**: Live updates for CPU, RAM, Disk, and Network usage.
- **Top Processes**: View the most memory-intensive processes currently running.
- **Hardware Details**: Automated detection of CPU model, RAM speed, and GPU load.
- **Interactive Desktop GUI**: Standalone frameless window support using `pywebview`.
- **Terminal Configuration**: Built-in menu for easy Host and Port management.
- **Cross-Platform**: Optimized for Windows, Linux, and Android (Termux).

## 📸 Screenshots

| Dashboard View | System Details |
| :---: | :---: |
| ![Dashboard](screenshots/dashboard.png) | ![System Details](screenshots/system_details.png) |


## 🛠️ Tech Stack

- **Backend**: Python, Flask, Gevent, SocketIO.
- **Frontend**: Tailwind CSS, Chart.js, Socket.IO Client.
- **Monitoring**: Psutil, GPUtil.
- **GUI**: PyWebView.

## 📦 Installation

### Prerequisites
- Python 3.7 or higher.
- NVIDIA Drivers (optional, for GPU load monitoring).

### Windows
1. Run the setup script to create a virtual environment and install dependencies:
   ```cmd
   setup.bat
   ```
2. Activate the environment:
   ```cmd
   .venv\Scripts\activate
   ```
3. Run the application:
   ```cmd
   python server_monitor.py
   ```

### Linux (Debian/Ubuntu)
1. Run the setup script (installs system dependencies for the GUI):
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
2. Activate the environment and run:
   ```bash
   source .venv/bin/activate
   python3 server_monitor.py
   ```

### Android (Termux)
1. Install **Termux** (recommended via F-Droid).
2. Update the environment and install Python along with build tools:
   ```bash
   pkg update && pkg upgrade
   pkg install python clang make
   ```
3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the monitoring server:
   ```bash
   python server_monitor.py
   ```
   *Note: On Termux, the app will automatically fall back to browser mode. Use the Local IP provided in the terminal to access the dashboard from your mobile browser.*

## 🏗️ Building the Executable (Windows)

To bundle the application into a single standalone `.exe` file with UPX compression:
```cmd
.\build_exe.bat
```
The output will be located in the `dist/` folder.

## 📂 Project Structure

```text
server_monitor/
├── monitor_core/       # Core hardware monitoring and utility logic
├── static/             # Frontend assets (CSS, JS, Icons)
├── templates/          # HTML templates (Jinja2)
├── server_monitor.py   # Application entry point & server logic
├── setup.py            # Package metadata
├── requirements.txt    # Project dependencies
├── build_exe.bat       # Windows build script
└── setup.bat/sh        # Installation scripts
```

## 📝 License

MIT License. Developed by KJAYDev.