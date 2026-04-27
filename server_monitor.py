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
    get_cpu_percent, get_temperature, get_ram_info, get_disk_percent,
    get_system_uptime, get_external_latency, get_top_processes, get_gpu_load,
    get_cpu_model, get_gpu_name, get_ram_details, get_network_speed,
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
    return format_duration((datetime.now() - APP_START_TIME).total_seconds())

@app.route('/')
def index():
    try:
        total, _, _ = shutil.disk_usage("/")
        ram_speed, ram_form = get_ram_details()
        return render_template(
            'dashboard.html',
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