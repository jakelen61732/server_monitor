import os
import json
import sys
import socket
import platform
import time
import urllib.request
import webbrowser

CONFIG_FILE = "config.json"

def get_config_path():
    """Returns a writable path for the config file on all platforms."""
    # ANDROID_PRIVATE_PATH is set by python-for-android
    base_path = os.environ.get('ANDROID_PRIVATE_PATH', os.path.abspath("."))
    return os.path.join(base_path, CONFIG_FILE)

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_config():
    """Loads host and port from config.json if it exists."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"host": "127.0.0.1", "port": 3000}

def save_config(host, port):
    """Saves the current host and port to config.json."""
    config_path = get_config_path()
    try:
        with open(config_path, 'w') as f:
            json.dump({"host": host, "port": port}, f, indent=4)
    except Exception as e:
        print(f"[ERROR] Could not save config: {e}")

def detect_os():
    """Robust OS detection including Termux and release info."""
    if 'com.termux' in os.environ.get('PREFIX', '') or os.path.exists('/data/data/com.termux'):
        return "Android (Termux)"
    elif platform.system() == "Darwin":
        return "macOS"
    else:
        return f"{platform.system()} {platform.release()}"

def format_bytes(size):
    """Formats bytes into human-readable strings."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

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
    if seconds > 0 or not uptime_str: uptime_str.append(f"{seconds}s")
    return " ".join(uptime_str)

def get_local_ip():
    """Attempts to find the local IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def ensure_port_available(host, preferred_port):
    """Checks if the port is busy and returns an available one if necessary."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, preferred_port))
            return preferred_port
    except socket.error:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

def launch_browser(host, port):
    """Opens the browser once the local health endpoint is responsive."""
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.getcode() == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.5)