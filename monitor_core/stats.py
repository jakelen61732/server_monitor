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
_last_temp_val = None
_last_temp_time = 0
last_net_io = None
last_net_time = time.time()
_lhm_computer = None
_last_lhm_refresh = 0
_disk_size_cache = {}
_proc_io_cache = {}

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

def shutdown_lhm():
    """Closes the LibreHardwareMonitor handle."""
    global _lhm_computer
    if _lhm_computer is not None:
        try:
            _lhm_computer.Close()
            _lhm_computer = None
        except Exception:
            pass

def get_motherboard_name():
    """Identifies the motherboard model via LHM or sysfs."""
    if _init_lhm():
        try:
            for hardware in _lhm_computer.Hardware:
                if hardware.HardwareType.ToString() == "Motherboard":
                    return hardware.Name
        except Exception: pass
    
    if platform.system() == "Linux":
        for path in ["/sys/class/dmi/id/board_name", "/sys/class/dmi/id/product_name"]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return f.read().strip()
                except Exception: pass
    return None

def get_storage_info():
    """Returns physical storage devices with realtime throughput and capacity info from LHM."""
    global _disk_size_cache
    devices = []
    if _init_lhm():
        _refresh_lhm()
        
        # One-time detection of physical disk sizes on Windows
        if not _disk_size_cache and platform.system() == "Windows":
            try:
                cmd = 'wmic diskdrive get caption,size /format:list'
                # WMIC output often contains null bytes or inconsistent line endings
                raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
                try:
                    output = raw_output.decode('utf-8', errors='ignore')
                except:
                    output = raw_output.decode('cp437', errors='ignore')
                
                caption = None
                for line in output.splitlines():
                    line = line.strip()
                    if not line: continue
                    if line.startswith('Caption='):
                        caption = line.split('=', 1)[1].strip()
                    elif line.startswith('Size=') and caption:
                        size_val = line.split('=', 1)[1].strip()
                        if size_val.isdigit():
                            # Aggressive normalization for the cache key
                            clean_cap = caption.lower().replace("ata device", "").replace("usb device", "").replace("nvme", "").strip()
                            _disk_size_cache[clean_cap] = int(size_val)
            except: pass

        try:
            for hardware in _lhm_computer.Hardware:
                if hardware.HardwareType.ToString() == "Storage":
                    temp, r_speed, w_speed, health, tbw, used_pct, lhm_size_gb, lhm_free_gb = None, None, None, None, None, None, None, None
                    for s in hardware.Sensors:
                        if s.Value is None: continue
                        stype, val, sname = s.SensorType.ToString(), float(s.Value), s.Name.lower()
                        if stype == "Temperature": temp = round(val, 1)
                        elif stype == "Throughput":
                            if "Read" in s.Name: r_speed = format_bytes(val)
                            elif "Write" in s.Name: w_speed = format_bytes(val)
                        elif stype == "Level":
                            if "Life" in s.Name or "Health" in s.Name: health = round(val, 1)
                            elif "Used Space" in s.Name: used_pct = val
                        elif stype in ["Data", "SmallData"]:
                            if "writes" in sname or "written" in sname:
                                tbw = format_bytes(val * (1024**3))
                            elif "remaining" in sname or "available" in sname or "free" in sname:
                                lhm_free_gb = val
                            elif "size" in sname or "capacity" in sname or "total" in sname:
                                lhm_size_gb = val
                    
                    # 1. Use LHM detected size as primary (Matches LHM GUI values)
                    total_gb = round(lhm_size_gb, 1) if lhm_size_gb is not None else 0
                    
                    # 2. Secondary fallback to fuzzy matched WMI physical sizes (Common for SATA/HDD)
                    if total_gb <= 0:
                        lhm_name_clean = hardware.Name.lower().replace("ata device", "").replace("usb device", "").replace("nvme", "").strip()
                        for wmi_caption, wmi_size in _disk_size_cache.items():
                            # Check if either name contains the other to bridge name mismatches
                            if lhm_name_clean and wmi_caption and (lhm_name_clean in wmi_caption or wmi_caption in lhm_name_clean):
                                total_gb = round(wmi_size / (1024**3), 1)
                                break

                    # 3. Use direct LHM free space sensor or calculate from percentage fallback
                    if lhm_free_gb is not None:
                        free_gb = round(lhm_free_gb, 1)
                    else:
                        free_gb = round(total_gb * (1 - (used_pct or 0) / 100), 1) if total_gb > 0 else 0

                    devices.append({
                        "name": hardware.Name, "temp": temp, "read": r_speed, "write": w_speed,
                        "health": health, "tbw": tbw, "total_gb": total_gb, "free_gb": free_gb,
                        "total_str": format_bytes(total_gb * (1024**3)) if total_gb > 0 else "N/A",
                        "free_str": format_bytes(free_gb * (1024**3)) if total_gb > 0 else "N/A"
                    })
        except Exception: pass
    return devices

def get_storage_stats():
    """Returns aggregated physical storage stats and the device list."""
    storage_list = get_storage_info()
    storage_total = round(sum(d['total_gb'] for d in storage_list), 1)
    storage_free = round(sum(d['free_gb'] for d in storage_list), 1)
    
    # Fallback to system disk info if physical detection fails or returns 0
    if storage_total == 0:
        _, disk_f_bytes, disk_t_bytes = get_disk_info()
        storage_total = round(disk_t_bytes / (1024**3), 1)
        storage_free = round(disk_f_bytes / (1024**3), 1)
        
    return storage_list, storage_total, storage_free

def get_memory_lhm_info():
    """Returns detailed memory sensors (load/temp) from LHM with numbering."""
    sensors = []
    if _init_lhm():
        _refresh_lhm()
        try:
            mem_idx = 0
            for hardware in _lhm_computer.Hardware:
                if hardware.HardwareType.ToString() == "Memory":
                    mem_idx += 1
                    for sensor in hardware.Sensors:
                        if sensor.Value is None: continue
                        s_type = sensor.SensorType.ToString()
                        val = round(float(sensor.Value), 1)
                        sensor_label = "" if sensor.Name == "Memory" else f" {sensor.Name}"
                        name = f"Memory {mem_idx}{sensor_label}"
                        if s_type == "Load":
                            sensors.append({"name": name, "value": f"{val}%"})
                        elif s_type == "Temperature":
                            sensors.append({"name": name, "value": f"{val}°C"})
        except Exception: pass
    return sensors

def get_network_names():
    """Returns a list of network adapter names from LHM."""
    if not _init_lhm():
        return None
    names = []
    try:
        for hardware in _lhm_computer.Hardware:
            if hardware.HardwareType.ToString() == "Network":
                names.append(hardware.Name)
    except Exception: pass
    return names if names else None

def check_storage_data_status():
    """Checks if any storage devices are missing Health or TBW reporting."""
    drives = get_storage_info()
    missing_info = []
    for d in drives:
        missing = []
        if d.get('health') is None:
            missing.append("Health/Life %")
        if d.get('tbw') is None:
            missing.append("TBW (Data Written)")
        
        if missing:
            missing_info.append({
                "name": d['name'],
                "missing": missing
            })
    return missing_info

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
    return None

def get_gpu_load():
    # 1. Use LHM if available
    if _init_lhm():
        _refresh_lhm()
        try:
            for hardware in _lhm_computer.Hardware:
                if "Gpu" in hardware.HardwareType.ToString():
                    for sensor in hardware.Sensors:
                        if sensor.SensorType.ToString() == "Load" and "GPU Core" in sensor.Name:
                            return float(sensor.Value)
        except Exception: pass

    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus: return gpus[0].load * 100
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
                            return float(sensor.Value) / 1000
        except Exception: pass

    # 2. Fallback to psutil
    if HAS_PSUTIL:
        try:
            freq = psutil.cpu_freq()
            if freq:
                return freq.current / 1000
        except Exception: pass
    return None

def get_temperature():
    global _last_temp_val, _last_temp_time
    now = time.time()

    # 1. Use LHM if available (Fastest & avoids PowerShell overhead)
    if _init_lhm():
        _refresh_lhm()
        try:
            for hardware in _lhm_computer.Hardware:
                for sensor in hardware.Sensors:
                    if sensor.SensorType.ToString() == "Temperature" and ("Package" in sensor.Name or "Average" in sensor.Name):
                        _last_temp_val = float(sensor.Value)
                        return _last_temp_val
        except Exception: pass

    if _last_temp_val is not None and now - _last_temp_time < 5: return _last_temp_val
    if platform.system() == "Windows":
        try:
            cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature).CurrentTemperature"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if output:
                _last_temp_val = (float(output) / 10.0) - 273.15
                _last_temp_time = now
                return _last_temp_val
        except Exception: pass
    elif HAS_PSUTIL:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ['coretemp', 'cpu_thermal', 'soc_thermal', 'acpitz']:
                    if name in temps:
                        _last_temp_val = temps[name][0].current
                        _last_temp_time = now
                        return _last_temp_val
        except Exception: pass
    return None

def get_ram_info():
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        return round(mem.percent, 1), mem.used, mem.total
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            meminfo = {l.split(':')[0]: int(l.split(':')[1].split()[0]) for l in lines}
            total_bytes = meminfo.get('MemTotal', 0) * 1024
            available_bytes = meminfo.get('MemAvailable', meminfo.get('MemFree', 0)) * 1024
            used_bytes = total_bytes - available_bytes
            percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0.0
            return percent, used_bytes, total_bytes
        except Exception: pass
    return 0.0, 0, 0

def get_disk_info():
    if HAS_PSUTIL:
        try:
            usage = psutil.disk_usage('/')
            return round(usage.percent, 1), usage.free, usage.total
        except Exception: pass
    try:
        total, used, free = shutil.disk_usage("/")
        return round((used / total) * 100, 1), free, total
    except Exception: pass
    return 0.0, 0, 0

def get_cpu_model():
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0]
        except Exception: pass
    res = platform.processor()
    return res if res and res != "Unknown" else None

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
    if not HAS_PSUTIL: return {"up": None, "down": None}
    now = time.time()
    io_now = psutil.net_io_counters()
    if last_net_io is None:
        last_net_io, last_net_time = io_now, now
        return {"up": 0.0, "down": 0.0}
    dt = now - last_net_time
    sent = (io_now.bytes_sent - last_net_io.bytes_sent) / dt if dt > 0 else 0.0
    recv = (io_now.bytes_recv - last_net_io.bytes_recv) / dt if dt > 0 else 0.0
    last_net_io, last_net_time = io_now, now
    return {"up": sent, "down": recv}

def get_system_uptime():
    if HAS_PSUTIL: return time.time() - psutil.boot_time()
    if platform.system() == "Linux" or "Android" in CURRENT_OS:
        try:
            with open('/proc/uptime', 'r') as f:
                return float(f.readline().split()[0])
        except Exception: pass
    return None

def get_external_latency():
    try:
        start = time.time()
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        return round((time.time() - start) * 1000, 1)
    except Exception: return None

def get_top_processes():
    if not HAS_PSUTIL: return {"list": [], "count": 0}
    global _proc_io_cache
    
    groups = {}
    total_count = 0
    now = time.time()
    num_cores = psutil.cpu_count() or 1

    for p in psutil.process_iter(['name', 'memory_info', 'cpu_percent', 'io_counters']):
        total_count += 1
        try:
            raw_name = p.info['name'] or "Unknown"
            # Strip extension for a cleaner look
            name = raw_name.rsplit('.', 1)[0] if '.' in raw_name else raw_name
            
            mem = p.info['memory_info'].rss if p.info['memory_info'] else 0
            # Normalize CPU usage by core count so 100% represents total system capacity
            cpu = (p.info['cpu_percent'] or 0.0) / num_cores
            
            # Disk Speed Calculation
            io = p.info['io_counters']
            disk_speed = 0
            if io:
                curr_io = io.read_bytes + io.write_bytes
                if name in _proc_io_cache:
                    last_io, last_time = _proc_io_cache[name]
                    td = now - last_time
                    if td > 0:
                        disk_speed = max(0, (curr_io - last_io) / td)
                _proc_io_cache[name] = (curr_io, now)

            group_key = name.lower()
            if group_key not in groups:
                groups[group_key] = {
                    'name': name,
                    'count': 1,
                    'memory': mem,
                    'cpu': cpu,
                    'disk': disk_speed
                }
            else:
                groups[group_key]['count'] += 1
                groups[group_key]['memory'] += mem
                groups[group_key]['cpu'] += cpu
                groups[group_key]['disk'] += disk_speed

        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue
    
    # Sort by memory and take top 10 grouped apps
    top = sorted(groups.values(), key=lambda x: x['memory'], reverse=True)[:10]
    
    # Final formatting for the frontend
    formatted_list = []
    for g in top:
        formatted_list.append({
            "name": g['name'],
            "count": g['count'],
            "cpu": round(min(g['cpu'], 100.0), 1),
            "memory_str": format_bytes(g['memory']),
            "disk_str": f"{format_bytes(g['disk'])}/s"
        })

    return {
        "list": formatted_list,
        "count": total_count
    }

def get_power_stats():
    """
    Fetches power and fan metrics via LibreHardwareMonitor (Windows) 
    or falls back to IPMI (Server).
    """
    # 1. Try LibreHardwareMonitor (High accuracy for Windows Desktop/Laptops)
    if _init_lhm():
        _refresh_lhm()
        try:
            stats = {"watts": 0.0, "voltage": 0.0, "amps": 0.0, "fan_rpm": 0, "gpu_temp": 0.0}
            cpu_pwr, gpu_pwr = 0.0, 0.0
            found_any = False
            
            def update_recursive(hw_item):
                nonlocal found_any, cpu_pwr, gpu_pwr
                h_type = hw_item.HardwareType.ToString()
                for sensor in hw_item.Sensors:
                    if sensor.Value is None: continue
                    
                    s_type = sensor.SensorType.ToString()
                    val = float(sensor.Value)
                    sname = sensor.Name.lower()
                    
                    if s_type == "Power":
                        # Prioritize Package/Total to avoid double-counting individual cores
                        if "cpu package" in sname:
                            cpu_pwr = val
                        elif "gpu power" in sname or ("gpu" in h_type and "power" in sname):
                            gpu_pwr = val
                        elif cpu_pwr == 0 and "cpu" in h_type and "total" in sname:
                            cpu_pwr = val
                        found_any = True

                    elif s_type == "Voltage":
                        # Prioritize 12V Rail for a realistic "System Current" calculation
                        if "12v" in sname:
                            stats["voltage"] = val
                        elif stats["voltage"] < 10 and ("vcore" in sname or "cpu core" in sname or stats["voltage"] == 0):
                            # Fallback to VCore if 12V isn't reported by the board
                            stats["voltage"] = val
                        found_any = True

                    elif s_type == "Current":
                        # Only use Current sensors that represent a total output
                        if "total" in sname or "output" in sname:
                            stats["amps"] = val
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
            
            # Sum the prioritized components
            stats["watts"] = cpu_pwr + gpu_pwr

            if found_any:
                # If no dedicated Amps sensor was found, calculate based on the best voltage we found
                if stats["amps"] == 0 and stats["voltage"] > 0:
                    stats["amps"] = stats["watts"] / stats["voltage"]
                return stats
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
            "amps": watts / 230 if watts else 0,
            "fan_rpm": 0,
            "gpu_temp": 0
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
        freq = get_cpu_freq()
        print(f"Result: {f'{freq:.1f} GHz' if freq is not None else 'N/A'}")

        print("\n[4] Reading Temperature...")
        temp = get_temperature()
        print(f"Result: {f'{temp:.1f}°C' if temp is not None else '--°C'}")

        print("\n[5] Reading Motherboard...")
        print(f"Result: {get_motherboard_name()}")

        print("\n[6] Reading Storage Stats (Free / Total)...")
        d_list, s_total, s_free = get_storage_stats()
        print(f"Total Capacity: {s_free} GB / {s_total} GB")
        for d in d_list:
            # Matches requested format: Name - {free}/{total}
            cap_str = f"{d['free_gb']} GB / {d['total_gb']} GB" if d['total_gb'] > 0 else "N/A (Physical size not found)"
            print(f" - {d['name']} - {cap_str}")
            
            meta_parts = []
            if d.get('temp'): meta_parts.append(f"Temp: {d['temp']}°C")
            if d.get('health'): meta_parts.append(f"Life: {d['health']}%")
            if d.get('tbw'): meta_parts.append(f"TBW: {d['tbw']}")
            if meta_parts: print(f"   { ' | '.join(meta_parts) }")
            
            if d.get('read') or d.get('write'):
                print(f"   Realtime -> R: {d['read'] or '0 B'}/s | W: {d['write'] or '0 B'}/s")

        print("\n[7] Reading Memory Details (LHM)...")
        print(f"Result: {get_memory_lhm_info()}")

        print("\n[8] Reading Network Adapters (LHM)...")
        print(f"Result: {get_network_names()}")

        print("\n[9] Reading GPU Info...")
        print(f"Name: {get_gpu_name()}")
        print(f"Load: {get_gpu_load()}%")

        print("\n[10] Storage SMART Compatibility Check...")
        missing_data = check_storage_data_status()
        if not missing_data:
            print("Result: OK - All drives reporting Health and TBW.")
        else:
            for item in missing_data:
                print(f"Warning: Drive '{item['name']}' is missing: {', '.join(item['missing'])}")
            print("Note: If metrics are missing, ensure you have the latest NVMe/SSD drivers installed.")

    print("\n[11] Reading Network Speed (Live Data)...")
    net_speed = get_network_speed()
    print(f"Result: Up: {format_bytes(net_speed['up'] or 0)}/s | Down: {format_bytes(net_speed['down'] or 0)}/s")

    print("\n=== Debug Complete ===")