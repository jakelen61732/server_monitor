import os
import time
import platform
import subprocess
import socket
import shutil
import json
from .utils import format_bytes, detect_os, format_duration

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

CURRENT_OS = detect_os()
_last_temp = "--°C"
_last_temp_time = 0
last_net_io = None
last_net_time = time.time()

def get_gpu_name():
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus: return gpus[0].name
        except Exception: pass
    if platform.system() == "Windows":
        try:
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_VideoController).Name"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output: return output
        except Exception: pass
    return "Not Detected"

def get_gpu_load():
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus: return round(gpus[0].load * 100, 1)
        except Exception: pass
    return None

def get_cpu_percent():
    if HAS_PSUTIL: return psutil.cpu_percent(interval=None)
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            load1 = os.getloadavg()[0]
            cores = os.cpu_count() or 1
            return round(min((load1 / cores) * 100, 100.0), 1)
        except Exception: pass
    return 0.0

def get_temperature():
    global _last_temp, _last_temp_time
    now = time.time()
    if now - _last_temp_time < 5: return _last_temp
    if platform.system() == "Windows":
        try:
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature).CurrentTemperature"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output:
                _last_temp = f"{round((float(output) / 10.0) - 273.15, 1)}°C"
                _last_temp_time = now
                return _last_temp
        except Exception: pass
    elif HAS_PSUTIL:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ['coretemp', 'cpu_thermal', 'soc_thermal', 'acpitz']:
                    if name in temps:
                        _last_temp = f"{round(temps[name][0].current, 1)}°C"
                        _last_temp_time = now
                        return _last_temp
        except Exception: pass
    return "--°C"

def get_ram_info():
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        return round(mem.percent, 1), round(mem.used / (1024**3), 2), round(mem.total / (1024**3), 2)
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            meminfo = {l.split(':')[0]: int(l.split(':')[1].split()[0]) for l in lines}
            total = meminfo.get('MemTotal', 0) / (1024**2)
            free = meminfo.get('MemAvailable', meminfo.get('MemFree', 0)) / (1024**2)
            used = total - free
            return round((used/total)*100, 1), round(used, 2), round(total, 2)
        except Exception: pass
    return 0.0, 0.0, 0.0

def get_disk_percent():
    if HAS_PSUTIL:
        try: return psutil.disk_usage('/').percent
        except Exception: return 0.0
    try:
        total, used, _ = shutil.disk_usage("/")
        return round((used / total) * 100, 1)
    except Exception: return 0.0

def get_cpu_model():
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0]
        except Exception: pass
    return platform.processor() or "Unknown"

def get_ram_details():
    speed, form = "Unknown", "Unknown"
    if platform.system() == "Windows":
        try:
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_PhysicalMemory | Select-Object Speed, FormFactor | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output:
                data = json.loads(output)
                item = data[0] if isinstance(data, list) else data
                speed = f"{item.get('Speed')} MHz" if item.get('Speed') else speed
                ff = str(item.get('FormFactor', '0'))
                form = "SODIMM" if ff == "12" else "DIMM" if ff == "8" else f"Type {ff}"
        except Exception: pass
    elif platform.system() == "Linux":
        try:
            # Try reading from sysfs for non-root access to some metadata
            if os.path.exists("/sys/class/dmi/id/chassis_type"):
                with open("/sys/class/dmi/id/chassis_type", "r") as f:
                    c_type = f.read().strip()
                    # Common chassis types: 8, 9, 10 are usually laptops (SODIMM)
                    form = "SODIMM" if c_type in ["8", "9", "10", "11", "14"] else "DIMM"
        except Exception: pass
    return speed, form

def get_network_speed():
    global last_net_io, last_net_time
    if not HAS_PSUTIL: return "N/A", "N/A"
    now = time.time()
    io_now = psutil.net_io_counters()
    if last_net_io is None:
        last_net_io, last_net_time = io_now, now
        return "0 B/s", "0 B/s"
    dt = now - last_net_time
    sent = (io_now.bytes_sent - last_net_io.bytes_sent) / dt
    recv = (io_now.bytes_recv - last_net_io.bytes_recv) / dt
    last_net_io, last_net_time = io_now, now
    return f"{format_bytes(sent)}/s", f"{format_bytes(recv)}/s"

def get_system_uptime():
    if HAS_PSUTIL: return format_duration(time.time() - psutil.boot_time())
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            with open('/proc/uptime', 'r') as f:
                return format_duration(float(f.readline().split()[0]))
        except Exception: pass
    return "N/A"

def get_external_latency():
    try:
        start = time.time()
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        return round((time.time() - start) * 1000, 1)
    except Exception: return None

def get_top_processes():
    if not HAS_PSUTIL: return []
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try: procs.append({'pid': p.info['pid'], 'name': p.info['name'], 'memory': p.info['memory_info'].rss})
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    top = sorted(procs, key=lambda x: x['memory'], reverse=True)[:5]
    return [{**p, 'memory_str': format_bytes(p['memory'])} for p in top]