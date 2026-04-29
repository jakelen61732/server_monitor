try:
    from gevent import monkey
    # thread=False is CRITICAL here. It allows the Flask server to run in a 
    # real OS thread while the main thread is blocked by the Webview GUI.
    monkey.patch_all(thread=False)
except ImportError:
    pass

import os
import threading
import platform
import webbrowser
import sys
import time
import shutil
import urllib.request
import socket
from threading import Lock
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO, emit

# Import core modules from the subfolder
from monitor_core.utils import (
    load_config, save_config, get_resource_path, detect_os, 
    format_duration, get_local_ip, ensure_port_available, format_bytes, launch_browser
)
from monitor_core.stats import (
    get_cpu_percent, get_temperature, get_ram_info, get_disk_info,
    get_system_uptime, get_external_latency, get_top_processes, get_gpu_load,
    get_cpu_model, get_gpu_name, get_ram_details, get_network_speed, get_power_stats, get_cpu_freq,
    get_motherboard_name, get_storage_stats, get_network_names, get_memory_lhm_info, shutdown_lhm,
    HAS_GPUTIL, HAS_PSUTIL
)

# Initialize Flask with the absolute path to the templates folder
app = Flask(__name__, 
            template_folder=get_resource_path('templates'))

socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode=None, # Automatically selects 'gevent' if available, otherwise 'threading'
    ping_timeout=60, 
    ping_interval=25
)

# Initialize global variables from config
_cfg = load_config()
SERVER_HOST = _cfg.get("host", "127.0.0.1")
SERVER_PORT = _cfg.get("port", 3000)
OPEN_EXTERNAL_BROWSER = _cfg.get("open_external", False)

# Threading control for background task
thread = None
thread_lock = Lock()

# Global variable to store the application start time
APP_START_TIME = datetime.now()

CURRENT_OS = detect_os()

try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

def get_app_uptime():
    return (datetime.now() - APP_START_TIME).total_seconds()

@app.route('/')
def index():
    try:
        storage_list, s_total_gb, s_free_gb = get_storage_stats()
        
        storage_info = {
            "list": storage_list,
            "total": format_bytes(s_total_gb * (1024**3)),
            "free": format_bytes(s_free_gb * (1024**3)),
            "summary": f"{format_bytes(s_free_gb * (1024**3))} / {format_bytes(s_total_gb * (1024**3))}"
        }

        ram_speed, ram_form = get_ram_details()
        
        # Refactor: format adapter descriptions in the route
        adapters_raw = get_network_names()
        network_list = [f"NIC: {name}" for name in adapters_raw] if adapters_raw else []

        # Centralized theme colors for Chart.js consistency
        chart_colors = {
            "grid": "#374151",
            "text": "#9ca3af",
            "cpu": "#f97316",
            "ram": "#3b82f6",
            "gpu": "#a855f7",
            "disk": "#22c55e",
            "power": "#eab308",
            "net_up": "#a855f7",
            "net_down": "#3b82f6"
        }

        return render_template(
            'dashboard.html',
            python_version=sys.version.split(" ")[0],
            os_info=CURRENT_OS,
            cpu_model=get_cpu_model() or "Unknown Processor",
            gpu_name=get_gpu_name() or "Not Detected",
            gpu_load_supported=HAS_GPUTIL,
            ram_speed=ram_speed,
            ram_form=ram_form,
            motherboard=get_motherboard_name() or "Generic Motherboard",
            storage=storage_info,
            memory_lhm=get_memory_lhm_info(),
            network_list=network_list,
            chart_colors=chart_colors,
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
            try:
                ram_percent, ram_used, ram_total = get_ram_info()
                disk_percent, disk_free_bytes, disk_total_bytes = get_disk_info()
                net_speed_raw = get_network_speed()
                
                power_raw = get_power_stats()
                power_data = None
                if power_raw:
                    power_data = {
                        **power_raw,
                        "watts_str": f"{power_raw['watts']:.1f} W",
                        "voltage_str": f"{power_raw['voltage']:.1f}V",
                        "amps_str": f"{power_raw['amps']:.2f}A",
                        "fan_str": f"{power_raw['fan_rpm']} RPM" if power_raw.get('fan_rpm', 0) > 0 else None,
                        "gpu_temp_str": f"GPU: {power_raw['gpu_temp']:.1f}°C" if power_raw.get('gpu_temp', 0) > 0 else None
                    }
                
                storage_list, storage_total_gb, storage_free_gb = get_storage_stats()

                cpu_freq_raw = get_cpu_freq()
                cpu_temp_raw = get_temperature()
                gpu_load_raw = get_gpu_load()
                sys_uptime_raw = get_system_uptime()

                ping_raw = get_external_latency()
                ping_data = None
                if ping_raw is not None:
                    if ping_raw < 100: p_color = "text-green-400"
                    elif ping_raw < 300: p_color = "text-yellow-400"
                    else: p_color = "text-red-400"
                    ping_data = {"display": f"{ping_raw:.1f}ms", "color": p_color}
                else:
                    ping_data = {"display": "Offline", "color": "text-red-600"}
                
                stats_data = {
                    "cpu": get_cpu_percent(),
                    "temp": f"{cpu_temp_raw:.1f}°C" if cpu_temp_raw is not None else None,
                    "cpu_freq": round(cpu_freq_raw, 1) if cpu_freq_raw is not None else None,
                    "ram": ram_percent,
                    "disk": disk_percent,
                    "disk_free": format_bytes(disk_free_bytes),
                    "disk_total": format_bytes(disk_total_bytes),
                    "ram_used": format_bytes(ram_used),
                    "ram_total": format_bytes(ram_total),
                    "net_up": f"{format_bytes(net_speed_raw['up'])}/s" if net_speed_raw['up'] is not None else "N/A",
                    "net_down": f"{format_bytes(net_speed_raw['down'])}/s" if net_speed_raw['down'] is not None else "N/A",
                    "net_up_raw": net_speed_raw['up'],
                    "net_down_raw": net_speed_raw['down'],
                    "system_uptime": format_duration(sys_uptime_raw) if sys_uptime_raw is not None else "N/A",
                    "app_uptime": format_duration(get_app_uptime()),
                    "internet_ping": ping_data,
                    "processes": get_top_processes(),
                    "gpu_load": f"{gpu_load_raw:.1f}%" if gpu_load_raw is not None else "N/A",
                    "gpu_load_raw": gpu_load_raw,
                    "power": power_data,
                    "storage_list": storage_list,
                    "storage_total": format_bytes(storage_total_gb * (1024**3)),
                    "storage_free": format_bytes(storage_free_gb * (1024**3))
                }
                
                # Broadcast to all connected clients
                socketio.emit('stats_response', stats_data)
            except Exception as e:
                print(f"[Thread Error] Intermittent monitoring failure: {e}")

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
    sys_uptime_raw = get_system_uptime()
    return jsonify({
        "status": "UP",
        "app_uptime": format_duration(get_app_uptime()),
        "system_uptime": format_duration(sys_uptime_raw) if sys_uptime_raw is not None else "N/A",
        "timestamp": datetime.now().isoformat()
    })

def run_server(host, port):
    """Runs the Flask-SocketIO server."""
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Automatically request Admin privileges on Windows for LibreHardwareMonitor access
    if platform.system() == "Windows":
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            # Relaunch the program with admin rights
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit(0)

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
        print(f" 5. Open External Browser [Current: {OPEN_EXTERNAL_BROWSER}]")
        print("-" * 40)
        print(" Press Ctrl+C to Exit")
        print("-" * 40)
        
        try:
            choice = input("Select an option (1-5): ").strip()
            
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
                        save_config(SERVER_HOST, SERVER_PORT, OPEN_EXTERNAL_BROWSER)
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
                            save_config(SERVER_HOST, SERVER_PORT, OPEN_EXTERNAL_BROWSER)
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

            elif choice == '5':
                OPEN_EXTERNAL_BROWSER = not OPEN_EXTERNAL_BROWSER
                save_config(SERVER_HOST, SERVER_PORT, OPEN_EXTERNAL_BROWSER)
                print(f"\n[INFO] Open External Browser set to: {OPEN_EXTERNAL_BROWSER}")
                time.sleep(1)

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
    
    try:
        if HAS_WEBVIEW and not OPEN_EXTERNAL_BROWSER:
            # Run server in a background thread so webview can take the main thread.
            threading.Thread(target=run_server, args=(SERVER_HOST, SERVER_PORT), daemon=True).start()
            
            class WebviewAPI:
                def __init__(self): self.window = None
                def close(self): 
                    if self.window: self.window.destroy()
                def minimize(self): 
                    if self.window: self.window.minimize()
                def toggle_maximize(self):
                    if not self.window: return
                    if not hasattr(self, '_is_maximized'): self._is_maximized = False
                    if self._is_maximized: self.window.restore()
                    else: self.window.maximize()
                    self._is_maximized = not self._is_maximized
                    return self._is_maximized

            api = WebviewAPI()
            print(f"[INFO] Launching Desktop Monitor: {url}")
            try:
                api.window = webview.create_window(
                    'Server Monitor', url, width=1200, height=900, min_size=(800, 600),
                    on_top=False, frameless=True, resizable=True, background_color='#111827',
                    js_api=api
                )
                try:
                    webview.start(gui='edgechromium')
                except Exception:
                    print("[INFO] 'edgechromium' engine not available, falling back to system default.")
                    webview.start()
            except Exception as e:
                print(f"[ERROR] PyWebView failed: {e}")
                webbrowser.open(url)
                while True: time.sleep(1)
        else:
            # Original browser-based flow
            threading.Thread(target=launch_browser, args=(SERVER_HOST, SERVER_PORT), daemon=True).start()
            run_server(SERVER_HOST, SERVER_PORT)
    except KeyboardInterrupt:
        print("\n[INFO] Monitor stopping...")
    finally:
        shutdown_lhm()
        # Use hard exit to prevent noisy pythonnet atexit tracebacks
        os._exit(0)