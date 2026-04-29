import os
import time
import platform
import subprocess
import socket
import shutil
import json
try:
    from .utils import format_bytes, detect_os, format_duration, get_resource_path
except ImportError:
    from utils import format_bytes, detect_os, format_duration, get_resource_path

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
    import pyghmi # type: ignore
    HAS_PYGHMI = True
except ImportError:
    HAS_PYGHMI = False

try:
    import clr
    HAS_PYTHONNET = True
except ImportError:
    HAS_PYTHONNET = False

CURRENT_OS = detect_os()
_last_temp = "--°C"
_last_temp_time = 0
last_net_io = None
last_net_time = time.time()
_lhm_computer = None
_last_lhm_refresh = 0

def _init_lhm():
    """Initializes LibreHardwareMonitor for Windows metrics."""
    global _lhm_computer
    if _lhm_computer is not None:
        return True
    if not HAS_PYTHONNET or platform.system() != "Windows":
        return False
    try:
        # get_resource_path already handles absolute pathing for both dev and bundled EXE modes
        dll_path = get_resource_path(os.path.join("lib", "LibreHardwareMonitorLib.dll"))

        if os.path.exists(dll_path):
            # Reference HidSharp if it exists (often a required dependency for LHM)
            hid_path = get_resource_path(os.path.join("lib", "HidSharp.dll"))
            if os.path.exists(hid_path):
                clr.AddReference(hid_path)

            clr.AddReference(dll_path)
            # Use the import style confirmed by successful direct test
            from LibreHardwareMonitor.Hardware import Computer # type: ignore
            
            _lhm_computer = Computer()
            _lhm_computer.IsCpuEnabled = True
            _lhm_computer.IsMotherboardEnabled = True
            _lhm_computer.IsGpuEnabled = True
            _lhm_computer.IsMemoryEnabled = True
            _lhm_computer.IsStorageEnabled = True
            _lhm_computer.IsNetworkEnabled = True
            _lhm_computer.IsPsuEnabled = True
            _lhm_computer.IsControllerEnabled = True
            _lhm_computer.Open()
            return True
    except Exception as e:
        if __name__ == "__main__":
            print(f"DEBUG: LHM Init Error: {e}")
    return False

def _refresh_lhm():
    """Recursive hardware refresh without relying on the brittle .NET Visitor interface."""
    global _lhm_computer, _last_lhm_refresh
    now = time.time()
    # Rate limit: Only poll drivers once per second to save CPU
    if now - _last_lhm_refresh < 0.8:
        return True

    if _lhm_computer:
        try:
            def update_recursive(hw):
                hw.Update()
                for sub in hw.SubHardware:
                    update_recursive(sub)
            
            for hardware in _lhm_computer.Hardware:
                update_recursive(hardware)
            
            _last_lhm_refresh = now
            return True
        except Exception: pass
    return False

def get_gpu_name():
    # 1. Use LHM if available (Most consistent with other hardware)
    if _init_lhm():
        try:
            for hardware in _lhm_computer.Hardware:
                h_type = hardware.HardwareType.ToString()
                if "Gpu" in h_type:
                    return hardware.Name
        except Exception: pass

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
    # 1. Use LHM if available
    if _init_lhm():
        _refresh_lhm()
        try:
            for hardware in _lhm_computer.Hardware:
                if "Gpu" in hardware.HardwareType.ToString():
                    for sensor in hardware.Sensors:
                        if sensor.SensorType.ToString() == "Load" and "GPU Core" in sensor.Name:
                            return round(float(sensor.Value), 1)
        except Exception: pass

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

def get_cpu_freq():
    # 1. Use LHM if available (Highest accuracy)
    if _init_lhm():
        _refresh_lhm()
        try:
            for hardware in _lhm_computer.Hardware:
                if hardware.HardwareType.ToString() == "Cpu":
                    for sensor in hardware.Sensors:
                        if sensor.SensorType.ToString() == "Clock" and "Core #1" in sensor.Name:
                            return round(float(sensor.Value) / 1000, 1)
        except Exception: pass

    # 2. Fallback to psutil
    if HAS_PSUTIL:
        try:
            freq = psutil.cpu_freq()
            if freq:
                return round(freq.current / 1000, 1)
        except Exception: pass
    return None

def get_temperature():
    global _last_temp, _last_temp_time
    now = time.time()

    # 1. Use LHM if available (Fastest & avoids PowerShell overhead)
    if _init_lhm():
        _refresh_lhm()
        try:
            for hardware in _lhm_computer.Hardware:
                for sensor in hardware.Sensors:
                    if sensor.SensorType.ToString() == "Temperature" and ("Package" in sensor.Name or "Average" in sensor.Name):
                        _last_temp = f"{round(float(sensor.Value), 1)}°C"
                        return _last_temp
        except Exception: pass

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

def get_disk_info():
    if HAS_PSUTIL:
        try:
            usage = psutil.disk_usage('/')
            return round(usage.percent, 1), round(usage.free / (1024**3), 2), round(usage.total / (1024**3), 2)
        except Exception: pass
    try:
        total, used, free = shutil.disk_usage("/")
        return round((used / total) * 100, 1), round(free / (1024**3), 2), round(total / (1024**3), 2)
    except Exception: pass
    return 0.0, 0.0, 0.0

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
    if not HAS_PSUTIL: return "N/A", "N/A", 0, 0
    now = time.time()
    io_now = psutil.net_io_counters()
    if last_net_io is None:
        last_net_io, last_net_time = io_now, now
        return "0 B/s", "0 B/s", 0, 0
    dt = now - last_net_time
    sent = (io_now.bytes_sent - last_net_io.bytes_sent) / dt
    recv = (io_now.bytes_recv - last_net_io.bytes_recv) / dt
    last_net_io, last_net_time = io_now, now
    return f"{format_bytes(sent)}/s", f"{format_bytes(recv)}/s", sent, recv

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

def get_power_stats():
    """
    Fetches power and fan metrics via LibreHardwareMonitor (Windows) 
    or falls back to IPMI (Server).
    """
    # 1. Try LibreHardwareMonitor (High accuracy for Windows Desktop/Laptops)
    if _init_lhm():
        _refresh_lhm()
        try:
            stats = {"watts": 0, "voltage": 0, "amps": 0, "fan_rpm": 0, "gpu_temp": 0}
            found_any = False
            
            def update_recursive(hw_item):
                nonlocal found_any
                h_type = hw_item.HardwareType.ToString()
                for sensor in hw_item.Sensors:
                    if sensor.Value is None: continue
                    
                    # Use String names as confirmed by lhm_direct_test.py
                    s_type = sensor.SensorType.ToString()
                    val = float(sensor.Value)
                    
                    if s_type == "Power":
                        stats["watts"] += val
                        found_any = True
                    elif s_type == "Voltage":
                        # Prioritize VCore or the first voltage found
                        if stats["voltage"] == 0 or "Core" in sensor.Name:
                            stats["voltage"] = val
                        found_any = True
                    elif s_type == "Current":
                        stats["amps"] += val
                        found_any = True
                    elif s_type == "Fan":
                        stats["fan_rpm"] = max(stats["fan_rpm"], int(val))
                        found_any = True
                    elif s_type == "Temperature" and "Gpu" in h_type:
                        stats["gpu_temp"] = max(stats["gpu_temp"], val)
                        found_any = True
                
                for sub_hw in hw_item.SubHardware:
                    update_recursive(sub_hw)

            for hardware in _lhm_computer.Hardware:
                update_recursive(hardware)
            
            if found_any:
                if stats["amps"] == 0 and stats["voltage"] > 0:
                    stats["amps"] = stats["watts"] / stats["voltage"]
                return {
                    "watts": round(stats["watts"], 1),
                    "voltage": round(stats["voltage"], 1),
                    "amps": round(stats["amps"], 2),
                    "fan_rpm": stats["fan_rpm"],
                    "gpu_temp": round(stats["gpu_temp"], 1)
                }
        except Exception: pass

    # 2. Fallback to IPMI (pyghmi) for server hardware
    if not HAS_PYGHMI:
        return None
    try:
        from pyghmi.ipmi import command # Local import to prevent EXE crash
        # Attempts to connect to the local BMC
        bmc = command.Command()
        p_data = bmc.get_power() # Returns {'status': 'on', 'current_power': ...}
        
        # Most BMCs provide 'current_power' in Watts. 
        # Voltage and Amps often require specific sensor lookups.
        watts = p_data.get('current_power', 0)
        return {
            "watts": watts,
            "voltage": 230, # Default or sensor-derived
            "amps": round(watts / 230, 2) if watts else 0,
            "fan_rpm": 0
        }
    except Exception:
        return None

if __name__ == "__main__":
    # This block allows you to run 'python monitor_core/stats.py' directly
    print("=== Stats.py Direct Debug ===")
    print(f"OS Detected: {CURRENT_OS}")
    print("\n--- Dependency Check ---")
    print(f"psutil:    {'OK' if HAS_PSUTIL else 'MISSING'}")
    print(f"GPUtil:    {'OK' if HAS_GPUTIL else 'MISSING'}")
    print(f"pythonnet: {'OK' if HAS_PYTHONNET else 'MISSING'}")
    print(f"pyghmi:    {'OK' if HAS_PYGHMI else 'MISSING'}")
    
    if platform.system() == "Windows":
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        print(f"Administrator Privileges: {'YES' if is_admin else 'NO'}")
        if not is_admin:
            print("[!] WARNING: LHM requires Admin rights to see most sensors.")

    print("\n[1] Initializing LHM...")
    lhm_ok = _init_lhm()
    print(f"LHM Init: {'SUCCESS' if lhm_ok else 'FAILED'}")

    if lhm_ok:
        print("\n[2] Reading Power Stats...")
        print(f"Result: {get_power_stats()}")

        print("\n[3] Reading CPU Freq...")
        print(f"Result: {get_cpu_freq()} GHz")

        print("\n[4] Reading Temperature...")
        print(f"Result: {get_temperature()}")

    print("\n[5] Reading Network...")
    print(f"Result: {get_network_speed()}")

    print("\n=== Debug Complete ===")