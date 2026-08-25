"""
Optimizer GUI - Backend (FastAPI)
====================================
Exposes every optimization as a callable action via a generic /api/execute
endpoint, described by a schema at /api/menu so the Next.js frontend can
render forms dynamically without hardcoding each one.

Run: uvicorn main:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import winreg
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import psutil
except ImportError:
    print("Missing dependency: pip install psutil")
    sys.exit(1)

app = FastAPI(title="Optimizer GUI Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://localhost:1420", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

IS_WINDOWS = sys.platform == "win32"

PRIORITY_CLASSES = {
    "idle": 0x00000040, "below_normal": 0x00004000, "normal": 0x00000020,
    "above_normal": 0x00008000, "high": 0x00000080, "realtime": 0x00000100,
} if IS_WINDOWS else {}

IO_PRIORITY_LEVELS = {"very_low": 0, "low": 1, "normal": 2, "high": 3}

POWER_PLAN_GUIDS = {
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
}
ULTIMATE_PERFORMANCE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"
PROCESS_MODE_BACKGROUND_BEGIN = 0x00100000


def win_run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def require_windows() -> None:
    if not IS_WINDOWS:
        raise HTTPException(400, "This action only works on Windows.")


def find_process(name_query: str) -> psutil.Process:
    query = name_query.lower()
    for p in psutil.process_iter(["pid", "name"]):
        if query in (p.info["name"] or "").lower():
            return psutil.Process(p.info["pid"])
    raise HTTPException(404, f"No running process matching '{name_query}'.")


def registry_set(hive: int, path: str, name: str, value: Any, value_type: int) -> None:
    key = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, name, 0, value_type, value)
    winreg.CloseKey(key)


# ===========================================================================
# ACTION IMPLEMENTATIONS  (params: dict -> str result message)
# ===========================================================================

def act_list_processes(_: dict) -> str:
    rows = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            rows.append(f"{p.info['pid']:>6}  {p.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return "\n".join(sorted(rows, key=lambda r: r.split()[-1].lower()))


def act_set_affinity(params: dict) -> str:
    require_windows()
    proc = find_process(params["process"])
    cores = sorted({int(c) for c in params["cores"]})
    total = psutil.cpu_count()
    if not cores or any(c < 0 or c >= total for c in cores):
        raise HTTPException(400, "Invalid core numbers.")
    proc.cpu_affinity(cores)
    remaining = [c for c in range(total) if c not in cores]
    return f"Assigned cores {cores} to {proc.name()}. Remaining for system: {remaining}"


def act_set_priority(params: dict) -> str:
    require_windows()
    proc = find_process(params["process"])
    level = params["level"]
    proc.nice(PRIORITY_CLASSES[level])
    return f"Set {proc.name()} priority to {level.replace('_', ' ')}."


def act_efficiency_mode(params: dict) -> str:
    require_windows()
    proc = find_process(params["process"])
    handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, proc.pid)
    if not handle:
        raise HTTPException(403, "Access denied - run as Administrator.")
    ok = ctypes.windll.kernel32.SetPriorityClass(handle, PROCESS_MODE_BACKGROUND_BEGIN)
    ctypes.windll.kernel32.CloseHandle(handle)
    if not ok:
        raise HTTPException(500, "Failed to set Efficiency Mode.")
    return f"Efficiency Mode enabled for {proc.name()}."


def act_io_priority(params: dict) -> str:
    require_windows()
    proc = find_process(params["process"])
    handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, proc.pid)
    if not handle:
        raise HTTPException(403, "Access denied - run as Administrator.")
    value = ctypes.c_ulong(IO_PRIORITY_LEVELS[params["level"]])
    status = ctypes.windll.ntdll.NtSetInformationProcess(handle, 33, ctypes.byref(value), ctypes.sizeof(value))
    ctypes.windll.kernel32.CloseHandle(handle)
    if status != 0:
        raise HTTPException(500, f"Failed (status={status}).")
    return f"I/O priority set to {params['level'].replace('_', ' ')} for {proc.name()}."


def act_trim_ram(params: dict) -> str:
    require_windows()
    proc = find_process(params["process"])
    handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
    if not handle:
        raise HTTPException(403, "Access denied - run as Administrator.")
    ok = ctypes.windll.psapi.EmptyWorkingSet(handle)
    ctypes.windll.kernel32.CloseHandle(handle)
    if not ok:
        raise HTTPException(500, "Failed to trim working set.")
    return f"Working set (RAM) trimmed for {proc.name()}."


def act_fullscreen_opt(params: dict) -> str:
    require_windows()
    path = params["path"]
    registry_set(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers",
        path, "~ HIGHDPIAWARE DISABLEDXMAXIMIZEDWINDOWEDMODE", winreg.REG_SZ,
    )
    return f"Fullscreen Optimizations disabled for {path}."


def act_gpu_preference(params: dict) -> str:
    require_windows()
    path, mode = params["path"], params["mode"]
    key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    if mode == "auto":
        try:
            winreg.DeleteValue(key, path)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return f"GPU preference override removed for {path}."
    pref = "1" if mode == "power_saving" else "2"
    winreg.SetValueEx(key, path, 0, winreg.REG_SZ, f"GpuPreference={pref};")
    winreg.CloseKey(key)
    return f"Set {path} to {mode.replace('_', ' ')}."


def act_compat_assistant(params: dict) -> str:
    require_windows()
    path = params["path"]
    registry_set(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers",
        path, "~ RUNASADMIN", winreg.REG_SZ,
    )
    return f"Compatibility Assistant flag applied for {path}."


def act_persistent_affinity(params: dict) -> str:
    require_windows()
    path = params["path"]
    cores = sorted({int(c) for c in params["cores"]})
    exe_name = path.split("\\")[-1]
    mask = sum(1 << c for c in cores)
    task_name = f"OptimizerAffinity_{exe_name.replace('.', '_')}"
    ps_command = (
        f"$mask={mask}; Get-Process -Name '{exe_name.replace('.exe', '')}' -ErrorAction SilentlyContinue "
        f"| ForEach-Object {{ $_.ProcessorAffinity = [IntPtr]$mask }}"
    )
    result = win_run([
        "schtasks", "/Create", "/TN", task_name, "/TR",
        f'powershell.exe -WindowStyle Hidden -Command "{ps_command}"',
        "/SC", "ONLOGON", "/RL", "HIGHEST", "/F",
    ])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return f"Scheduled task '{task_name}' created - cores {cores} auto-applied on every login."


def act_high_dpi(params: dict) -> str:
    require_windows()
    path = params["path"]
    registry_set(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers",
        path, "~ HIGHDPIAWARE", winreg.REG_SZ,
    )
    return f"High DPI override applied for {path}."


def act_power_plan(params: dict) -> str:
    require_windows()
    plan = params["plan"]
    result = win_run(["powercfg", "/setactive", POWER_PLAN_GUIDS[plan]])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return f"Switched to {plan.replace('_', ' ')}."


def act_ultimate_performance(_: dict) -> str:
    require_windows()
    result = win_run(["powercfg", "-duplicatescheme", ULTIMATE_PERFORMANCE_GUID])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return "Ultimate Performance power plan unlocked."


def act_processor_state(params: dict) -> str:
    require_windows()
    win_run(["powercfg", "-setacvalueindex", "scheme_current", "sub_processor", "PROCTHROTTLEMIN", str(params["min"])])
    win_run(["powercfg", "-setacvalueindex", "scheme_current", "sub_processor", "PROCTHROTTLEMAX", str(params["max"])])
    win_run(["powercfg", "-setactive", "scheme_current"])
    return f"Processor state limits applied: min={params['min']}%, max={params['max']}%."


def act_core_parking(_: dict) -> str:
    require_windows()
    win_run(["powercfg", "-setacvalueindex", "scheme_current", "sub_processor", "CPMINCORES", "100"])
    win_run(["powercfg", "-setactive", "scheme_current"])
    return "CPU core parking disabled."


def act_disable_hibernation(_: dict) -> str:
    require_windows()
    win_run(["powercfg", "/hibernate", "off"])
    return "Hibernation disabled."


def act_disable_fast_startup(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
                 "HiberbootEnabled", 0, winreg.REG_DWORD)
    return "Fast Startup disabled."


def act_disable_usb_suspend(_: dict) -> str:
    require_windows()
    win_run(["powercfg", "/setacvalueindex", "scheme_current",
             "2a737441-1930-4402-8d77-b2bebba308a3", "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "0"])
    win_run(["powercfg", "-setactive", "scheme_current"])
    return "USB selective suspend disabled."


def act_timer_resolution(_: dict) -> str:
    require_windows()
    resolution, current = ctypes.c_ulong(5000), ctypes.c_ulong()
    status = ctypes.windll.ntdll.NtSetTimerResolution(resolution, True, ctypes.byref(current))
    if status != 0:
        raise HTTPException(500, f"Failed (status={status}).")
    return f"Timer resolution set to {current.value / 10000:.2f}ms (reverts when backend process exits)."


def act_flush_dns(_: dict) -> str:
    require_windows()
    return win_run(["ipconfig", "/flushdns"]).stdout


def act_reset_winsock(_: dict) -> str:
    require_windows()
    return win_run(["netsh", "winsock", "reset"]).stdout + " Restart required."


def act_disable_nagle(_: dict) -> str:
    require_windows()
    base = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    count = 0
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as interfaces:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(interfaces, i)
            except OSError:
                break
            i += 1
            try:
                sub_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{sub}", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(sub_key, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(sub_key, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(sub_key)
                count += 1
            except PermissionError:
                pass
    return f"Nagle's algorithm disabled on {count} interface(s). Restart required."


def act_disable_network_throttling(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                 "NetworkThrottlingIndex", 0xFFFFFFFF, winreg.REG_DWORD)
    return "Network throttling disabled."


def act_system_responsiveness(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                 "SystemResponsiveness", 0, winreg.REG_DWORD)
    return "SystemResponsiveness set to 0."


def act_prioritize_games(_: dict) -> str:
    require_windows()
    path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
    registry_set(winreg.HKEY_LOCAL_MACHINE, path, "GPU Priority", 8, winreg.REG_DWORD)
    registry_set(winreg.HKEY_LOCAL_MACHINE, path, "Priority", 6, winreg.REG_DWORD)
    registry_set(winreg.HKEY_LOCAL_MACHINE, path, "Scheduling Category", "High", winreg.REG_SZ)
    registry_set(winreg.HKEY_LOCAL_MACHINE, path, "SFIO Priority", "High", winreg.REG_SZ)
    return "Games task priority raised in MMCSS scheduler."


def act_visual_effects(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\explorer\VisualEffects",
                 "VisualFXSetting", 2, winreg.REG_DWORD)
    return "Visual effects set to Best Performance."


def act_disable_transparency(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                 "EnableTransparency", 0, winreg.REG_DWORD)
    return "Transparency effects disabled."


def act_disable_sysmain(_: dict) -> str:
    require_windows()
    win_run(["net", "stop", "SysMain"])
    win_run(["sc", "config", "SysMain", "start=", "disabled"])
    return "SysMain (Superfetch) disabled."


def act_disable_search_indexing(_: dict) -> str:
    require_windows()
    win_run(["net", "stop", "WSearch"])
    win_run(["sc", "config", "WSearch", "start=", "disabled"])
    return "Windows Search indexing disabled."


def act_disable_telemetry(_: dict) -> str:
    require_windows()
    win_run(["net", "stop", "DiagTrack"])
    win_run(["sc", "config", "DiagTrack", "start=", "disabled"])
    return "Telemetry service (DiagTrack) disabled."


def act_disable_gamedvr(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled", 0, winreg.REG_DWORD)
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
                 "AllowGameDVR", 0, winreg.REG_DWORD)
    return "Game DVR / background recording disabled."


def act_disable_gamebar(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled", 0, winreg.REG_DWORD)
    registry_set(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                 "AppCaptureEnabled", 0, winreg.REG_DWORD)
    return "Xbox Game Bar overlay disabled."


def act_disable_storage_sense(_: dict) -> str:
    require_windows()
    registry_set(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy",
                 "01", 0, winreg.REG_DWORD)
    return "Storage Sense disabled."


def act_hags_toggle(params: dict) -> str:
    require_windows()
    value = 2 if params["enable"] else 1
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                 "HwSchMode", value, winreg.REG_DWORD)
    return f"Hardware GPU Scheduling {'enabled' if params['enable'] else 'disabled'}. Restart required."


def act_optimize_drive(params: dict) -> str:
    require_windows()
    drive = params["drive"].rstrip(":")
    result = win_run(["defrag", f"{drive}:", "/O"])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return result.stdout


def act_pagefile(params: dict) -> str:
    require_windows()
    drive = params["drive"].rstrip(":") + ":"
    initial, maximum = params["initial"], params["max"]
    ps_command = (
        f"$cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges; "
        f"$cs.AutomaticManagedPagefile = $false; $cs.Put(); "
        f"$pf = Get-WmiObject Win32_PageFileSetting -Filter \"name='{drive}\\\\pagefile.sys'\"; "
        f"if (-not $pf) {{ Set-WmiInstance Win32_PageFileSetting -Arguments "
        f"@{{name='{drive}\\\\pagefile.sys'; InitialSize={initial}; MaximumSize={maximum}}} }} "
        f"else {{ $pf.InitialSize={initial}; $pf.MaximumSize={maximum}; $pf.Put() }}"
    )
    result = win_run(["powershell.exe", "-Command", ps_command])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return f"Page file on {drive} set to {initial}MB-{maximum}MB. Restart required."


def act_disable_mitigations(params: dict) -> str:
    require_windows()
    if not params.get("confirm"):
        raise HTTPException(400, "Confirmation required - this reduces system security.")
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
                 "FeatureSettingsOverride", 3, winreg.REG_DWORD)
    registry_set(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
                 "FeatureSettingsOverrideMask", 3, winreg.REG_DWORD)
    return "Spectre/Meltdown mitigations disabled. Restart required."


def act_disable_dynamic_tick(_: dict) -> str:
    require_windows()
    win_run(["bcdedit", "/deletevalue", "useplatformclock"])
    result = win_run(["bcdedit", "/set", "disabledynamictick", "yes"])
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return "Dynamic tick / HPET disabled. Restart required."


# ===========================================================================
# MENU SCHEMA - drives the frontend's dynamic forms
# ===========================================================================

MENU: list[dict[str, Any]] = [
    {"id": "process", "title": "Process Control", "items": [
        {"id": "list", "label": "List running processes", "params": []},
        {"id": "affinity", "label": "Set CPU core affinity", "params": [
            {"name": "process", "type": "process_select", "label": "Program"},
            {"name": "cores", "type": "core_multiselect", "label": "Cores to assign"},
        ]},
        {"id": "priority", "label": "Set CPU priority", "params": [
            {"name": "process", "type": "process_select", "label": "Program"},
            {"name": "level", "type": "select", "label": "Priority",
             "options": ["idle", "below_normal", "normal", "above_normal", "high", "realtime"]},
        ]},
        {"id": "efficiency", "label": "Enable Efficiency Mode", "params": [
            {"name": "process", "type": "process_select", "label": "Program"},
        ]},
        {"id": "io_priority", "label": "Set I/O priority", "params": [
            {"name": "process", "type": "process_select", "label": "Program"},
            {"name": "level", "type": "select", "label": "I/O priority",
             "options": ["very_low", "low", "normal", "high"]},
        ]},
        {"id": "trim_ram", "label": "Trim RAM (working set)", "params": [
            {"name": "process", "type": "process_select", "label": "Program"},
        ]},
        {"id": "fullscreen_opt", "label": "Disable Fullscreen Optimizations", "params": [
            {"name": "path", "type": "text", "label": "Full path to .exe"},
        ]},
        {"id": "gpu_preference", "label": "Set GPU preference", "params": [
            {"name": "path", "type": "text", "label": "Full path to .exe"},
            {"name": "mode", "type": "select", "label": "Mode",
             "options": ["power_saving", "high_performance", "auto"]},
        ]},
        {"id": "compat_assistant", "label": "Disable Compatibility Assistant", "params": [
            {"name": "path", "type": "text", "label": "Full path to .exe"},
        ]},
        {"id": "persistent_affinity", "label": "Auto-apply affinity on every launch", "params": [
            {"name": "path", "type": "text", "label": "Full path to .exe"},
            {"name": "cores", "type": "core_multiselect", "label": "Cores to pin"},
        ]},
        {"id": "high_dpi", "label": "Force High DPI awareness", "params": [
            {"name": "path", "type": "text", "label": "Full path to .exe"},
        ]},
    ]},
    {"id": "power", "title": "Power & CPU", "items": [
        {"id": "power_plan", "label": "Switch power plan", "params": [
            {"name": "plan", "type": "select", "label": "Plan",
             "options": ["high_performance", "balanced", "power_saver"]},
        ]},
        {"id": "ultimate_performance", "label": "Unlock Ultimate Performance plan", "params": []},
        {"id": "processor_state", "label": "Set min/max processor state", "params": [
            {"name": "min", "type": "number", "label": "Minimum %"},
            {"name": "max", "type": "number", "label": "Maximum %"},
        ]},
        {"id": "core_parking", "label": "Disable CPU core parking", "params": []},
        {"id": "disable_hibernation", "label": "Disable hibernation", "params": []},
        {"id": "disable_fast_startup", "label": "Disable Fast Startup", "params": []},
        {"id": "disable_usb_suspend", "label": "Disable USB selective suspend", "params": []},
        {"id": "timer_resolution", "label": "Lower system timer resolution", "params": []},
    ]},
    {"id": "network", "title": "Network", "items": [
        {"id": "flush_dns", "label": "Flush DNS cache", "params": []},
        {"id": "reset_winsock", "label": "Reset Winsock catalog", "params": []},
        {"id": "disable_nagle", "label": "Disable Nagle's algorithm", "params": []},
        {"id": "disable_throttling", "label": "Disable network throttling", "params": []},
        {"id": "system_responsiveness", "label": "Lower SystemResponsiveness", "params": []},
        {"id": "prioritize_games", "label": "Prioritize Games task (MMCSS)", "params": []},
    ]},
    {"id": "system", "title": "System & UI", "items": [
        {"id": "visual_effects", "label": "Visual effects: Best Performance", "params": []},
        {"id": "disable_transparency", "label": "Disable transparency effects", "params": []},
        {"id": "disable_sysmain", "label": "Disable SysMain/Superfetch", "params": []},
        {"id": "disable_search_indexing", "label": "Disable Search indexing", "params": []},
        {"id": "disable_telemetry", "label": "Disable telemetry (DiagTrack)", "params": []},
        {"id": "disable_gamedvr", "label": "Disable Game DVR", "params": []},
        {"id": "disable_gamebar", "label": "Disable Xbox Game Bar", "params": []},
        {"id": "disable_storage_sense", "label": "Disable Storage Sense", "params": []},
        {"id": "hags", "label": "Toggle Hardware GPU Scheduling", "params": [
            {"name": "enable", "type": "checkbox", "label": "Enable (unchecked = disable)"},
        ]},
    ]},
    {"id": "storage", "title": "Storage", "items": [
        {"id": "optimize_drive", "label": "Optimize/TRIM a drive", "params": [
            {"name": "drive", "type": "text", "label": "Drive letter (e.g. C)"},
        ]},
        {"id": "pagefile", "label": "Set custom page file size", "params": [
            {"name": "drive", "type": "text", "label": "Drive letter (e.g. C)"},
            {"name": "initial", "type": "number", "label": "Initial size (MB)"},
            {"name": "max", "type": "number", "label": "Maximum size (MB)"},
        ]},
    ]},
    {"id": "advanced", "title": "Advanced (security tradeoffs)", "items": [
        {"id": "disable_mitigations", "label": "Disable Spectre/Meltdown mitigations", "params": [
            {"name": "confirm", "type": "checkbox", "label": "I understand this reduces security"},
        ]},
        {"id": "disable_dynamic_tick", "label": "Disable dynamic tick / HPET", "params": []},
    ]},
]

ACTIONS: dict[str, Callable[[dict], str]] = {
    "process.list": act_list_processes,
    "process.affinity": act_set_affinity,
    "process.priority": act_set_priority,
    "process.efficiency": act_efficiency_mode,
    "process.io_priority": act_io_priority,
    "process.trim_ram": act_trim_ram,
    "process.fullscreen_opt": act_fullscreen_opt,
    "process.gpu_preference": act_gpu_preference,
    "process.compat_assistant": act_compat_assistant,
    "process.persistent_affinity": act_persistent_affinity,
    "process.high_dpi": act_high_dpi,
    "power.power_plan": act_power_plan,
    "power.ultimate_performance": act_ultimate_performance,
    "power.processor_state": act_processor_state,
    "power.core_parking": act_core_parking,
    "power.disable_hibernation": act_disable_hibernation,
    "power.disable_fast_startup": act_disable_fast_startup,
    "power.disable_usb_suspend": act_disable_usb_suspend,
    "power.timer_resolution": act_timer_resolution,
    "network.flush_dns": act_flush_dns,
    "network.reset_winsock": act_reset_winsock,
    "network.disable_nagle": act_disable_nagle,
    "network.disable_throttling": act_disable_network_throttling,
    "network.system_responsiveness": act_system_responsiveness,
    "network.prioritize_games": act_prioritize_games,
    "system.visual_effects": act_visual_effects,
    "system.disable_transparency": act_disable_transparency,
    "system.disable_sysmain": act_disable_sysmain,
    "system.disable_search_indexing": act_disable_search_indexing,
    "system.disable_telemetry": act_disable_telemetry,
    "system.disable_gamedvr": act_disable_gamedvr,
    "system.disable_gamebar": act_disable_gamebar,
    "system.disable_storage_sense": act_disable_storage_sense,
    "system.hags": act_hags_toggle,
    "storage.optimize_drive": act_optimize_drive,
    "storage.pagefile": act_pagefile,
    "advanced.disable_mitigations": act_disable_mitigations,
    "advanced.disable_dynamic_tick": act_disable_dynamic_tick,
}


class ExecuteRequest(BaseModel):
    category: str
    item: str
    params: dict[str, Any] = {}


@app.get("/api/menu")
async def get_menu() -> list[dict[str, Any]]:
    return MENU


@app.get("/api/cpu-count")
async def get_cpu_count() -> dict[str, int]:
    return {"count": psutil.cpu_count()}


@app.get("/api/processes")
async def get_processes() -> list[dict[str, str]]:
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            out.append({"pid": str(p.info["pid"]), "name": p.info["name"] or "?"})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(out, key=lambda r: r["name"].lower())


@app.get("/api/admin-status")
async def admin_status() -> dict[str, bool]:
    if not IS_WINDOWS:
        return {"is_admin": False}
    try:
        return {"is_admin": bool(ctypes.windll.shell32.IsUserAnAdmin())}
    except Exception:
        return {"is_admin": False}


@app.post("/api/execute")
async def execute(req: ExecuteRequest) -> dict[str, str]:
    key = f"{req.category}.{req.item}"
    func = ACTIONS.get(key)
    if func is None:
        raise HTTPException(404, f"Unknown action: {key}")
    message = func(req.params)
    return {"message": message}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
