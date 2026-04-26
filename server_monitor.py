try:
    from gevent import monkey
    # thread=False is CRITICAL here. It allows the Flask server to run in a 
    # real OS thread while the main thread is blocked by the Webview GUI.
    monkey.patch_all(thread=False)
except ImportError:
    pass

import shutil
import socket
import os
import json
import threading
import urllib.request
import subprocess
import platform
import webbrowser
import sys
import time
from threading import Lock
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='gevent',
    ping_timeout=60, 
    ping_interval=25
)

CONFIG_FILE = "config.json"

def load_config():
    """Loads host and port from config.json if it exists."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"host": "127.0.0.1", "port": 3000}

def save_config(host, port):
    """Saves the current host and port to config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"host": host, "port": port}, f, indent=4)
    except Exception as e:
        print(f"[ERROR] Could not save config: {e}")

# Initialize global variables from config
_cfg = load_config()
SERVER_HOST = _cfg.get("host", "127.0.0.1")
SERVER_PORT = _cfg.get("port", 3000)

# Threading control for background task
thread = None
thread_lock = Lock()

# Global variable to store the application start time
APP_START_TIME = datetime.now()

# Global variables for network tracking
last_net_io = None
last_net_time = time.time()

# --- Robust OS Detection ---
def detect_os():
    # Check specifically for Termux environment
    if 'com.termux' in os.environ.get('PREFIX', '') or os.path.exists('/data/data/com.termux'):
        return "Android (Termux)"
    elif platform.system() == "Darwin":
        return "macOS"
    else:
        # Returns "Windows 10", "Linux 5.15", etc.
        return f"{platform.system()} {platform.release()}"

CURRENT_OS = detect_os()

# --- Cross-Platform Hardware Readers ---

# Attempt to load psutil (Standard for Desktop OS)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

def get_gpu_name():
    """Retrieves the GPU model name with fallbacks."""
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus: return gpus[0].name
        except Exception: pass
    
    if platform.system() == "Windows":
        try:
            # Modern PowerShell replacement for wmic
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_VideoController).Name"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output: return output
        except Exception: pass
    return "Not Detected"

def get_gpu_load():
    """Retrieves current GPU usage percentage."""
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus: return round(gpus[0].load * 100, 1)
        except Exception: pass
    return None

def get_cpu_percent():
    if HAS_PSUTIL:
        return psutil.cpu_percent(interval=None)
    
    # Native Fallback strictly for Linux/Android environments
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            load1, _, _ = os.getloadavg()
            cores = os.cpu_count() or 1
            usage = (load1 / cores) * 100
            return round(min(usage, 100.0), 1)
        except Exception:
            return 0.0
            
    return 0.0  # Safe fallback for Windows/Mac without psutil

_last_temp = "--°C"
_last_temp_time = 0

def get_temperature():
    """Retrieves the CPU/System temperature (Cross-platform)."""
    global _last_temp, _last_temp_time
    now = time.time()
    
    # Spawning PowerShell processes is heavy. Cache the result for 5 seconds to prevent GUI lag.
    if now - _last_temp_time < 5:
        return _last_temp

    if platform.system() == "Windows":
        try:
            # Requires Admin privileges on many systems
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature).CurrentTemperature"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output:
                # Convert from tenths of Kelvin to Celsius
                temp = (float(output) / 10.0) - 273.15
                _last_temp = f"{round(temp, 1)}°C"
                _last_temp_time = now
                return _last_temp
        except Exception:
            pass
    elif HAS_PSUTIL:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try common sensor keys for Linux/macOS
                for name in ['coretemp', 'cpu_thermal', 'soc_thermal', 'acpitz']:
                    if name in temps:
                        _last_temp = f"{round(temps[name][0].current, 1)}°C"
                        _last_temp_time = now
                        return _last_temp
                # Fallback to the first detected sensor
                first_key = list(temps.keys())[0]
                _last_temp = f"{round(temps[first_key][0].current, 1)}°C"
                _last_temp_time = now
                return _last_temp
        except Exception: pass
    return "--°C"

def get_ram_info():
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        used_gb = mem.used / (1024**3)
        return round(mem.percent, 1), round(used_gb, 2), round(total_gb, 2)
    
    # Native Fallback strictly for Linux/Android environments
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0].strip())
            
            total_gb = meminfo.get('MemTotal', 0) / (1024**2)
            available_gb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0)) / (1024**2)
            used_gb = total_gb - available_gb
            percent = (used_gb / total_gb) * 100 if total_gb > 0 else 0
            
            return round(percent, 1), round(used_gb, 2), round(total_gb, 2)
        except Exception:
            return 0.0, 0.0, 0.0
            
    return 0.0, 0.0, 0.0  # Safe fallback for Windows/Mac without psutil

def get_disk_percent():
    """Calculates disk usage percentage for the root partition."""
    if HAS_PSUTIL:
        try:
            return psutil.disk_usage('/').percent
        except Exception:
            return 0.0
    
    # Standard library fallback using shutil
    try:
        total, used, free = shutil.disk_usage("/")
        return round((used / total) * 100, 1)
    except Exception:
        return 0.0

def get_cpu_model():
    """Attempts to get a descriptive CPU model name."""
    try:
        if platform.system() == "Windows":
            # Use registry for a clean CPU name on Windows
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0]
        elif platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
    except Exception:
        pass
    # Fallback to generic platform info
    return platform.processor() or "Unknown"

def get_ram_details():
    """Retrieves RAM speed and form factor (Windows specific)."""
    speed = "Unknown"
    form_factor = "Unknown"
    if platform.system() == "Windows":
        try:
            # Modern PowerShell approach (wmic is deprecated on Win 11)
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_PhysicalMemory | Select-Object Speed, FormFactor | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output:
                import json
                data = json.loads(output)
                # Handle cases with multiple RAM sticks vs single stick
                first_stick = data[0] if isinstance(data, list) else data
                
                speed_val = first_stick.get('Speed')
                if speed_val: speed = f"{speed_val} MHz"
                
                ff_code = str(first_stick.get('FormFactor', '0'))
                # Mapping standard SMBIOS form factor codes
                if ff_code == "12": form_factor = "SODIMM"
                elif ff_code == "8": form_factor = "DIMM"
                else: form_factor = f"Type {ff_code}"
        except Exception:
            pass
    return speed, form_factor

def format_bytes(size):
    """Formats bytes into human-readable strings."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

def get_network_speed():
    """Calculates upload and download speeds."""
    global last_net_io, last_net_time
    
    if HAS_PSUTIL:
        now = time.time()
        io_now = psutil.net_io_counters()
        
        if last_net_io is None:
            last_net_io = io_now
            last_net_time = now
            return "0 B/s", "0 B/s"

        dt = now - last_net_time
        if dt <= 0: return "0 B/s", "0 B/s"

        sent_speed = (io_now.bytes_sent - last_net_io.bytes_sent) / dt
        recv_speed = (io_now.bytes_recv - last_net_io.bytes_recv) / dt

        last_net_io = io_now
        last_net_time = now

        return f"{format_bytes(sent_speed)}/s", f"{format_bytes(recv_speed)}/s"
    
    return "N/A", "N/A"

def get_external_latency():
    """Measures the time to establish a connection to a reliable external target (Google DNS)."""
    try:
        start_time = time.time()
        # Using port 53 (DNS) as it is almost always open and highly responsive
        # This is a TCP handshake check, which is more reliable across platforms than ICMP
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        return round((time.time() - start_time) * 1000, 1)
    except Exception:
        return None

def get_top_processes():
    """Retrieves the top 5 memory-intensive processes."""
    if not HAS_PSUTIL:
        return []
    
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            pinfo = proc.info
            processes.append({
                'pid': pinfo['pid'],
                'name': pinfo['name'],
                'memory': pinfo['memory_info'].rss
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # Sort by memory usage descending and take top 5
    top_5 = sorted(processes, key=lambda x: x['memory'], reverse=True)[:5]
    return [{**p, 'memory_str': format_bytes(p['memory'])} for p in top_5]

# Initialize Network IO
get_network_speed()
# Initialize CPU baseline so the first read isn't 0%
get_cpu_percent()
time.sleep(0.1)

# --- Utility functions for uptime calculation ---
def format_duration(uptime_seconds):
    """Formats seconds into a human-readable string."""
    days = int(uptime_seconds // (24 * 3600))
    uptime_seconds %= (24 * 3600)
    hours = int(uptime_seconds // 3600)
    uptime_seconds %= 3600
    minutes = int(uptime_seconds // 60)
    seconds = int(uptime_seconds % 60)

    uptime_str = []
    if days > 0: uptime_str.append(f"{days}d")
    if hours > 0: uptime_str.append(f"{hours}h")
    if minutes > 0: uptime_str.append(f"{minutes}m")
    if seconds > 0 or not uptime_str: uptime_str.append(f"{seconds}s") # Ensure seconds are shown if nothing else, or for short uptimes
    return " ".join(uptime_str)

def get_app_uptime():
    return format_duration((datetime.now() - APP_START_TIME).total_seconds())

def get_system_uptime():
    """Retrieves system uptime using psutil or native fallbacks."""
    if HAS_PSUTIL:
        boot_time = psutil.boot_time()
        return format_duration(time.time() - boot_time)
    
    # Fallback for Linux/Android (Termux)
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                return format_duration(uptime_seconds)
        except Exception:
            return "Unknown"
            
    return "N/A"

# --- Web Server ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Server Monitor</title>
    <style>
        body { background-color: #111827; margin: 0; font-family: sans-serif; overflow: hidden; }
        #loading-overlay {
            position: fixed;
            inset: 0;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background-color: #111827;
            transition: opacity 0.5s ease;
        }
        .spinner { width: 48px; height: 48px; border: 4px solid #4ade80; border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
    <script src="/static/tailwind.min.js"></script>
</head>
<body id="main-body" class="bg-gray-900 text-white min-h-screen flex flex-col p-0 m-0 overflow-y-auto cursor-default">
    <div id="loading-overlay">
        <div class="spinner"></div>
        <p class="text-gray-400 font-mono text-sm animate-pulse">Initializing Monitor...</p>
    </div>

    <div class="relative bg-gray-800 border-b border-gray-700 flex items-center justify-between px-4 py-1.5 select-none shrink-0 h-10">
        <div class="pywebview-drag-region absolute top-[5px] inset-x-[5px] bottom-0 cursor-move z-0"></div>
        <div class="flex items-center gap-2 pointer-events-none relative z-10">
            <img src="/favicon.ico" class="w-4 h-4 opacity-80" alt="logo">
            <span class="text-[11px] font-bold text-gray-500 tracking-wider uppercase">Server Monitor</span>
        </div>
        <div class="flex items-center gap-1 relative z-20">
            <button onclick="window.pywebview.api.minimize()" title="Minimize" class="p-1.5 hover:bg-gray-700 rounded-md transition-colors group">
                <svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M20 12H4"></path></svg>
            </button>
            <button id="maximize-btn" onclick="handleToggleMaximize()" title="Maximize" class="p-1.5 hover:bg-gray-700 rounded-md transition-colors group">
                <svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" stroke-width="2.5" stroke="currentColor" fill="none" /></svg>
            </button>
            <button onclick="window.pywebview.api.close()" title="Close" class="p-1.5 hover:bg-red-500/20 group rounded-md transition-colors">
                <svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    </div>

    <div class="flex-1 flex items-start md:items-center justify-center p-4 transition-all duration-500">
    <div class="bg-gray-800 shadow-xl rounded-2xl p-4 md:p-8 w-full max-w-5xl border border-gray-700 transition-all duration-500 ease-in-out transform-gpu will-change-transform">
        <div class="flex items-center justify-between mb-6">
            <h1 class="text-2xl font-bold text-green-400">Server Monitor</h1>
            <div class="flex items-center gap-2">
                <span class="text-xs text-gray-400 font-mono uppercase">Live</span>
                <span class="flex h-3 w-3">
                    <span class="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-green-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                </span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div class="space-y-6">
                <div class="grid grid-cols-3 gap-4">
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <div class="flex justify-between items-start">
                            <p class="text-xs text-gray-400 font-semibold mb-1 uppercase tracking-wider">CPU</p>
                            <span class="text-[10px] font-mono text-orange-400" id="cpu-temp">--°C</span>
                        </div>
                        <p class="text-2xl md:text-3xl font-bold" id="cpu-usage">--%</p>
                    </div>
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <p class="text-xs text-gray-400 font-semibold mb-1 uppercase tracking-wider">RAM</p>
                        <p class="text-2xl md:text-3xl font-bold" id="ram-usage">--%</p>
                    </div>
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <p class="text-xs text-gray-400 font-semibold mb-1 uppercase tracking-wider">Disk</p>
                        <p class="text-2xl md:text-3xl font-bold" id="disk-usage">--%</p>
                    </div>
                </div>

                <div class="bg-gray-700 p-4 rounded-lg">
                    <div class="flex justify-around text-center">
                        <div>
                            <p class="text-xs text-gray-400 font-semibold uppercase tracking-wider">Download</p>
                            <p class="text-lg font-mono text-blue-400" id="net-down">--</p>
                        </div>
                        <div class="border-l border-gray-600"></div>
                        <div>
                            <p class="text-xs text-gray-400 font-semibold uppercase tracking-wider">Upload</p>
                            <p class="text-lg font-mono text-purple-400" id="net-up">--</p>
                        </div>
                    </div>
                </div>

                <div class="h-48 lg:h-64">
                    <canvas id="cpuChart"></canvas>
                </div>
            </div>

            <div class="space-y-6">
                <div class="relative flex border-b border-gray-700">
                    <button onclick="switchTab('processes')" id="btn-processes" class="w-1/2 px-4 py-2 text-sm font-semibold text-green-400 transition-all">
                        Top Processes
                    </button>
                    <button onclick="switchTab('system')" id="btn-system" class="w-1/2 px-4 py-2 text-sm font-semibold text-gray-400 hover:text-white transition-all">
                        System Details
                    </button>
                    <div id="tab-indicator" class="absolute bottom-0 h-0.5 bg-green-400 transition-all duration-300 ease-in-out" style="width: 50%; left: 0;"></div>
                </div>

                <div class="overflow-hidden">
                    <div id="tab-wrapper" class="flex w-[200%] transition-transform duration-300 ease-in-out">
                        <div id="tab-processes" class="w-1/2 h-[450px] overflow-y-auto pr-2 custom-scrollbar">
                            <h2 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Top Processes (RAM)</h2>
                            <div class="bg-gray-700/50 rounded-lg overflow-hidden">
                                <table class="w-full text-xs text-left">
                                    <thead>
                                        <tr class="text-gray-500 border-b border-gray-600">
                                            <th class="px-4 py-2 font-semibold">PID</th>
                                            <th class="px-4 py-2 font-semibold">Process</th>
                                            <th class="px-4 py-2 text-right font-semibold">Usage</th>
                                        </tr>
                                    </thead>
                                    <tbody id="process-table" class="font-mono"></tbody>
                                </table>
                            </div>

                            <div class="space-y-3 text-sm border-t border-gray-700 pt-4 mt-6">
                                <div class="flex justify-between">
                                    <span class="text-gray-400">RAM Allocation:</span>
                                    <span class="font-mono" id="ram-details">-- GB / -- GB</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Internet Ping:</span>
                                    <span class="font-mono" id="internet-ping">--ms</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Browser Latency:</span>
                                    <span class="font-mono text-green-400" id="latency">--ms</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">System Uptime:</span>
                                    <span class="font-mono" id="system-uptime">--</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">App Uptime:</span>
                                    <span class="font-mono text-green-400" id="app-uptime">--</span>
                                </div>
                            </div>
                        </div>

                        <div id="tab-system" class="w-1/2 h-[450px] overflow-y-auto pr-2 custom-scrollbar">
                            <div class="space-y-4 pb-4">
                                <div class="bg-gray-700/30 p-4 rounded-lg border border-gray-700/50">
                                    <p class="text-[10px] text-gray-500 uppercase font-bold mb-1">Processor</p>
                                    <p class="text-sm font-mono text-blue-300 leading-relaxed">{{ cpu_model }}</p>
                                </div>
                                <div class="bg-gray-700/30 p-4 rounded-lg border border-gray-700/50">
                                    <p class="text-[10px] text-gray-500 uppercase font-bold mb-1">Storage Overview</p>
                                    <p class="text-sm font-mono">Total Capacity: <span class="text-green-400">{{ total_disk }}</span></p>
                                </div>
                                <div class="bg-gray-700/30 p-4 rounded-lg border border-gray-700/50">
                                    <p class="text-[10px] text-gray-500 uppercase font-bold mb-1">Graphics Unit</p>
                                    <div class="text-sm font-mono space-y-1">
                                        <p class="text-blue-300 leading-tight">{{ gpu_name }}</p>
                                        {% if gpu_load_supported %}
                                        <p>Usage: <span id="gpu-usage" class="text-green-400">--%</span></p>
                                        {% endif %}
                                    </div>
                                </div>
                                <div class="bg-gray-700/30 p-4 rounded-lg border border-gray-700/50">
                                    <p class="text-[10px] text-gray-500 uppercase font-bold mb-1">Memory Hardware</p>
                                    <div class="text-sm font-mono space-y-1">
                                        <p>Speed: <span class="text-blue-300">{{ ram_speed }}</span></p>
                                        <p>Form Factor: <span class="text-blue-300">{{ ram_form }}</span></p>
                                    </div>
                                </div>
                                <div class="bg-gray-700/30 p-4 rounded-lg border border-gray-700/50">
                                    <p class="text-[10px] text-gray-500 uppercase font-bold mb-1">Platform Details</p>
                                    <div class="text-sm font-mono space-y-1">
                                        <div class="flex justify-between"><span class="text-gray-400 text-xs uppercase">OS</span><span class="text-blue-300">{{ os_info }}</span></div>
                                        <div class="flex justify-between"><span class="text-gray-400 text-xs uppercase">Arch</span><span>{{ architecture }}</span></div>
                                        <div class="flex justify-between"><span class="text-gray-400 text-xs uppercase">Python</span><span>{{ python_version }}</span></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <style>
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        html, body {
            cursor: auto;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb { 
            background: #4b5563; 
            border-radius: 10px; 
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #4ade80; }
        .custom-scrollbar { scrollbar-width: thin; scrollbar-color: #4b5563 transparent; }

        button, a, .cursor-pointer, [onclick] {
            cursor: pointer !important;
        }
        .pywebview-drag-region {
            cursor: move !important;
        }
    </style>

    <script src="/static/chart.min.js"></script>
    <script src="/static/socket.io.min.js"></script>

    <script>
        const gpuSupported = {{ 'true' if gpu_load_supported else 'false' }};
        const ctx = document.getElementById('cpuChart').getContext('2d');
        
        const datasets = [
            {
                label: 'CPU %',
                data: Array(60).fill(0),
                borderColor: '#4ade80',
                backgroundColor: 'rgba(74, 222, 128, 0.1)',
                fill: true,
                tension: 0.2,
                cubicInterpolationMode: 'monotone',
                pointRadius: 0,
                clip: false,
                yAxisID: 'y'
            },
            {
                label: 'RAM %',
                data: Array(60).fill(0),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.2,
                cubicInterpolationMode: 'monotone',
                pointRadius: 0,
                clip: false,
                yAxisID: 'y'
            }
        ];

        const yAxes = {
            y: { 
                min: 0, 
                max: 100, 
                grid: { color: '#374151' },
                ticks: { color: '#9ca3af' },
                title: { display: true, text: 'CPU/RAM %', color: '#9ca3af', font: { size: 10 } }
            }
        };

        if (gpuSupported) {
            datasets.push({
                label: 'GPU %',
                data: Array(60).fill(0),
                borderColor: '#f97316',
                backgroundColor: 'rgba(249, 115, 22, 0.1)',
                fill: true,
                tension: 0.2,
                cubicInterpolationMode: 'monotone',
                pointRadius: 0,
                clip: false,
                yAxisID: 'y1'
            });
            yAxes.y1 = {
                min: 0,
                max: 100,
                position: 'right',
                grid: { drawOnChartArea: false },
                ticks: { color: '#f97316' },
                title: { display: true, text: 'GPU %', color: '#f97316', font: { size: 10 } }
            };
        }

        const cpuChart = new Chart(ctx, {
            type: 'line',
            data: { labels: Array(60).fill(''), datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: { left: 10, right: 0, top: 10, bottom: 0 }
                },
                scales: { ...yAxes, x: { display: false } },
                plugins: {
                    legend: { 
                        display: true,
                        labels: {
                            color: '#9ca3af',
                            boxWidth: 12,
                            font: { size: 10 }
                        }
                    }
                },
                animation: {
                    duration: 0,
                    easing: 'linear'
                }
            }
        });

        function switchTab(tab) {
            const wrapper = document.getElementById('tab-wrapper');
            const indicator = document.getElementById('tab-indicator');
            const procBtn = document.getElementById('btn-processes');
            const sysBtn = document.getElementById('btn-system');

            if (tab === 'processes') {
                wrapper.style.transform = 'translateX(0%)';
                indicator.style.left = '0%';
                procBtn.classList.add('text-green-400');
                procBtn.classList.remove('text-gray-400');
                sysBtn.classList.add('text-gray-400');
                sysBtn.classList.remove('text-green-400');
            } else {
                wrapper.style.transform = 'translateX(-50%)';
                indicator.style.left = '50%';
                sysBtn.classList.add('text-green-400');
                sysBtn.classList.remove('text-gray-400');
                procBtn.classList.add('text-gray-400');
                procBtn.classList.remove('text-green-400');
            }
        }

        async function handleToggleMaximize() {
            const isMaximized = await window.pywebview.api.toggle_maximize();
            const btn = document.getElementById('maximize-btn');
            if (isMaximized) {
                btn.title = "Restore";
                btn.innerHTML = `<svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M7 3h14v14M3 7h14v14H3z" /></svg>`;
            } else {
                btn.title = "Maximize";
                btn.innerHTML = `<svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" stroke-width="2.5" stroke="currentColor" fill="none" /></svg>`;
            }
        }

        const socket = io();

        setInterval(() => {
            socket.emit('ping_server', { startTime: performance.now() });
        }, 2000);

        socket.on('pong_client', (data) => {
            const ping = Math.round(performance.now() - data.startTime);
            const latencyElem = document.getElementById('latency');
            latencyElem.innerText = ping + 'ms';
            
            if (ping < 100) latencyElem.className = "font-mono text-green-400";
            else if (ping < 300) latencyElem.className = "font-mono text-yellow-400";
            else latencyElem.className = "font-mono text-red-400";
        });

        socket.on('stats_response', (data) => {
            const loader = document.getElementById('loading-overlay');
            if (loader) {
                loader.style.opacity = '0';
                setTimeout(() => {
                    loader.remove();
                    document.body.style.overflow = 'auto';
                }, 500);
            }

                document.getElementById('cpu-usage').innerText = data.cpu + '%';
                document.getElementById('cpu-temp').innerText = data.temp;
                document.getElementById('ram-usage').innerText = data.ram + '%';
                document.getElementById('disk-usage').innerText = data.disk + '%';
                document.getElementById('net-up').innerText = data.net_up;
                document.getElementById('net-down').innerText = data.net_down;
                document.getElementById('ram-details').innerText = data.ram_used + ' GB / ' + data.ram_total + ' GB';
                document.getElementById('system-uptime').innerText = data.system_uptime;
                document.getElementById('app-uptime').innerText = data.app_uptime;
                const gpuUsageElem = document.getElementById('gpu-usage');
                if (gpuUsageElem) gpuUsageElem.innerText = data.gpu_load !== null ? data.gpu_load + '%' : 'N/A';

                const extPingElem = document.getElementById('internet-ping');
                if (data.internet_ping !== null) {
                    extPingElem.innerText = data.internet_ping + 'ms';
                    if (data.internet_ping < 100) extPingElem.className = "font-mono text-green-400";
                    else if (data.internet_ping < 300) extPingElem.className = "font-mono text-yellow-400";
                    else extPingElem.className = "font-mono text-red-400";
                } else {
                    extPingElem.innerText = 'Offline';
                    extPingElem.className = "font-mono text-red-600";
                }

                const processTable = document.getElementById('process-table');
                processTable.innerHTML = data.processes.map(p => `
                    <tr class="border-b border-gray-700/50 last:border-0 hover:bg-gray-700 transition-colors">
                        <td class="px-4 py-1.5 text-gray-400">${p.pid}</td>
                        <td class="px-4 py-1.5 truncate max-w-[120px]">${p.name}</td>
                        <td class="px-4 py-1.5 text-right text-green-400">${p.memory_str}</td>
                    </tr>
                `).join('');

                cpuChart.data.datasets[0].data.push(data.cpu);
                cpuChart.data.datasets[0].data.shift();
                cpuChart.data.datasets[1].data.push(data.ram);
                cpuChart.data.datasets[1].data.shift();
                
                if (gpuSupported) {
                    const gpuVal = data.gpu_load ?? 0;
                    cpuChart.data.datasets[2].data.push(gpuVal);
                    cpuChart.data.datasets[2].data.shift();
                }
                
                cpuChart.update();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        total, _, _ = shutil.disk_usage("/")
        ram_speed, ram_form = get_ram_details()
        return render_template_string(
            HTML_TEMPLATE,
            python_version=sys.version.split(" ")[0],
            os_info=CURRENT_OS,
            cpu_model=get_cpu_model(),
            gpu_name=get_gpu_name(),
            gpu_load_supported=HAS_GPUTIL,
            ram_speed=ram_speed,
            ram_form=ram_form,
            total_disk=format_bytes(total),
            architecture=platform.machine(),
            server_host=SERVER_HOST if SERVER_HOST != "0.0.0.0" else "127.0.0.1",
            server_port=SERVER_PORT
        )
    except Exception as e:
        return f"Error loading monitor: {str(e)}", 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static assets (JS/CSS) from the bundled static directory."""
    return send_from_directory(
        get_resource_path('static'),
        filename
    )

@app.route('/favicon.ico')
def favicon():
    """Serves the favicon from the resource directory."""
    icon_path = get_resource_path('favicon.ico')
    return send_from_directory(
        os.path.dirname(icon_path),
        os.path.basename(icon_path),
        mimetype='image/vnd.microsoft.icon'
    )

def background_stats_thread():
    """
    A single background task that gathers data and broadcasts to all clients.
    This is much more efficient than per-client polling.
    """
    print("Starting background stats broadcast...")
    try:
        while True:
            ram_percent, ram_used, ram_total = get_ram_info()
            up, down = get_network_speed()
            
            stats_data = {
                "cpu": get_cpu_percent(),
                "temp": get_temperature(),
                "ram": ram_percent,
                "disk": get_disk_percent(),
                "ram_used": ram_used,
                "ram_total": ram_total,
                "net_up": up,
                "net_down": down,
                "system_uptime": get_system_uptime(),
                "app_uptime": get_app_uptime(),
                "internet_ping": get_external_latency(),
                "processes": get_top_processes(),
                "gpu_load": get_gpu_load()
            }
            
            # Broadcast to all connected clients
            socketio.emit('stats_response', stats_data)
            socketio.sleep(1) # Yield to other tasks for 1 second
    except (KeyboardInterrupt, SystemExit):
        print("\n[Thread] Background stats thread stopping...")

@socketio.on('connect')
def handle_connect():
    """Starts the background thread when the first client connects."""
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_stats_thread)

@socketio.on('ping_server')
def handle_ping(json_data):
    """Handles a tiny ping request to measure browser latency."""
    emit('pong_client', {'startTime': json_data.get('startTime')})

@app.route('/health')
def health_check():
    """
    Provides a simple health check endpoint.
    """
    return jsonify({
        "status": "UP",
        "app_uptime": get_app_uptime(),
        "system_uptime": get_system_uptime(),
        "timestamp": datetime.now().isoformat()
    })

def run_server(host, port):
    """Runs the Flask-SocketIO server."""
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def launch_browser(host, port):
    """Waits for the server to be ready and opens the default web browser."""
    print("[INFO] Waiting for dashboard to become available...")
    server_ready = False
    # If host is 0.0.0.0 (all interfaces), we open browser on local loopback
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    
    # Poll the health check endpoint for up to 15 seconds
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.getcode() == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.5)
    
    if server_ready:
        print(f"[SUCCESS] Server is live. Opening dashboard: {url}")
        webbrowser.open(url)
    else:
        print("[ERROR] The monitoring server failed to respond. Dashboard not opened.")

def get_local_ip():
    """Attempts to find the local IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't actually connect or send data, but finds the local interface
        # that would be used to reach an external IP.
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def ensure_port_available(host, preferred_port):
    """
    Checks if the preferred port is available on the specified host.
    If occupied, returns a random available port provided by the OS.
    """
    try:
        # Attempt to bind to the preferred port to check availability
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, preferred_port))
            return preferred_port
    except socket.error:
        # Port is busy, find a random available one by binding to port 0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

if __name__ == '__main__':
    # Detect if we have an interactive console (Standard mode vs Windowed mode)
    is_interactive = sys.stdin and sys.stdin.isatty()

    # Only show the configuration menu if running in a terminal
    while is_interactive:
        # Basic validation for "Ready" status
        is_host_valid = len(SERVER_HOST.split('.')) == 4 or SERVER_HOST == "localhost"
        is_port_valid = 1024 <= SERVER_PORT <= 65535
        status = "READY" if (is_host_valid and is_port_valid) else "NOT READY"

        os.system('cls' if platform.system() == 'Windows' else 'clear')
        print("="*40)
        print("   SERVER MONITOR CONFIGURATION")
        print("="*40)
        print(f" 1. Edit Host  [Current: {SERVER_HOST}]")
        print(f" 2. Edit Port  [Current: {SERVER_PORT}]")
        print(f" 3. Run Server [Status: {status}]")
        print(f" 4. Check Network Info")
        print("-" * 40)
        print(" Press Ctrl+C to Exit")
        print("-" * 40)
        
        try:
            choice = input("Select an option (1-4): ").strip()
            
            if choice == '1':
                print("\n--- Host Configuration ---")
                print("INFO: The host determines which network interfaces the server listens on.")
                print(" - 127.0.0.1: Only accessible from this computer (Private).")
                print(" - 0.0.0.0: Accessible from any device on your network (Public).")
                new_host = input(f"Enter new host [{SERVER_HOST}]: ").strip()
                if new_host:
                    try:
                        if new_host != "localhost":
                            socket.inet_aton(new_host)
                        SERVER_HOST = new_host
                        save_config(SERVER_HOST, SERVER_PORT)
                    except socket.error:
                        print("[ERROR] Invalid IP address format.")
                        time.sleep(1.5)
            
            elif choice == '2':
                print("\n--- Port Configuration ---")
                print("INFO: Choose a port between 1024 and 65535.")
                print("Avoid ports like 80 or 443 which usually require Admin privileges.")
                new_port = input(f"Enter new 4-digit port [{SERVER_PORT}]: ").strip()
                if new_port:
                    if new_port.isdigit():
                        p = int(new_port)
                        if 1024 <= p <= 65535:
                            SERVER_PORT = p
                            save_config(SERVER_HOST, SERVER_PORT)
                        else:
                            print("[ERROR] Port must be between 1024 and 65535.")
                            time.sleep(1.5)
                    else:
                        print("[ERROR] Port must be a numeric value.")
                        time.sleep(1.5)
            
            elif choice == '3':
                if status == "READY":
                    print(f"\n[INFO] Starting {CURRENT_OS} monitoring server...")
                    break
                else:
                    print("\n[ERROR] Configuration is invalid. Please fix Host or Port.")
                    time.sleep(1.5)
            
            elif choice == '4':
                print("\n--- Network Information ---")
                print(f" Device Name: {socket.gethostname()}")
                print(f" Local IP:    {get_local_ip()}")
                print(f" Loopback:    127.0.0.1")
                print("\n Use the Local IP if you want other devices to access the monitor.")
                input("\n Press Enter to return to menu...")

            else:
                print("\n[ERROR] Invalid selection.")
                time.sleep(1)
                
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            sys.exit(0)

    # Determine the UI URL
    # Using 'localhost' instead of '127.0.0.1' ensures DevTools sees a domain name.
    ui_host = "localhost" if SERVER_HOST in ["0.0.0.0", "127.0.0.1"] else SERVER_HOST

    # Ensure the chosen port is actually available before starting
    _original_port = SERVER_PORT
    SERVER_PORT = ensure_port_available(SERVER_HOST, SERVER_PORT)
    if SERVER_PORT != _original_port:
        print(f"[INFO] Port {_original_port} is busy. Automatically assigned available port: {SERVER_PORT}")

    url = f"http://{ui_host}:{SERVER_PORT}"
    
    if HAS_WEBVIEW:
        # Run server in a background thread so webview can take the main thread.
        # gevent's monkey patching ensures this thread behaves correctly with the hub.
        threading.Thread(target=run_server, args=(SERVER_HOST, SERVER_PORT), daemon=True).start()
        
        class WebviewAPI:
            """API exposed to the Javascript 'window.pywebview.api' object."""
            def __init__(self):
                self.window = None
            def close(self):
                if self.window: self.window.destroy()
            def minimize(self):
                if self.window: self.window.minimize()
            def toggle_maximize(self):
                if not self.window: return
                # pywebview doesn't expose a state check for maximization,
                # so we track it internally to provide a toggle effect.
                if not hasattr(self, '_is_maximized'): self._is_maximized = False
                if self._is_maximized:
                    self.window.restore()
                else:
                    self.window.maximize()
                self._is_maximized = not self._is_maximized
                return self._is_maximized

        api = WebviewAPI()
        print(f"[INFO] Launching Desktop Monitor: {url}")
        try:
            # Setting min_size helps the Windows Window Manager stabilize frameless resizing.
            api.window = webview.create_window(
                'Server Monitor', 
                url, 
                width=1200, 
                height=900, 
                min_size=(800, 600),
                on_top=False, 
                frameless=True, 
                resizable=True, 
                background_color='#111827',
                js_api=api
            )
            try:
                # Primary attempt: Force modern WebView2 (Edge Chromium)
                webview.start(gui='edgechromium')
            except Exception:
                # Secondary attempt: Let pywebview auto-detect (EdgeHTML or MSHTML fallback)
                print("[INFO] 'edgechromium' engine not available, falling back to system default.")
                webview.start()
        except Exception as e:
            print(f"[ERROR] PyWebView failed: {e}")
            # Fallback to standard browser if GUI fails to initialize
            webbrowser.open(url)
            while True: time.sleep(1)
    else:
        # Original browser-based flow
        threading.Thread(target=launch_browser, args=(SERVER_HOST, SERVER_PORT), daemon=True).start()
        try:
            run_server(SERVER_HOST, SERVER_PORT)
        except Exception as e:
            print(f"\n[CRITICAL] Server failed to start: {e}")
            if "10048" in str(e):
                print(f"[HINT] Port {SERVER_PORT} is already in use by another application.")
            input("\nPress Enter to exit...")