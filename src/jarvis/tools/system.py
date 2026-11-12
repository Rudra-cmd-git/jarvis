"""System controls: volume, media, brightness, status, power and settings."""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import time

import psutil

from jarvis.core.errors import ToolError
from jarvis.core.util import clamp, format_bytes
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec
from jarvis.tools.winutil import is_admin, media_key

logger = logging.getLogger("jarvis.tools.system")


# ---------------------------------------------------------------------- volume
def _com_audio():
    import comtypes

    comtypes.CoInitialize()
    from pycaw.pycaw import AudioUtilities

    endpoint = AudioUtilities.GetSpeakers().EndpointVolume
    if endpoint is None:
        raise ToolError("No audio output device is available")
    return endpoint


def _volume_percent() -> int:
    try:
        endpoint = _com_audio()
        return int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
    except Exception as exc:
        raise ToolError(f"Could not read system volume: {exc}") from exc
    finally:
        _co_uninit()


def _co_uninit() -> None:
    try:
        import comtypes

        comtypes.CoUninitialize()
    except Exception:
        pass


def _set_volume(ctx: ToolContext, percent: float | None = None, step: int | None = None) -> str:
    value: float
    if step is not None:
        value = _volume_percent() + step
    elif percent is not None:
        value = percent
    else:
        raise ToolError("Provide either 'percent' or 'step'.")
    value = clamp(value, 0, 100)
    try:
        endpoint = _com_audio()
        endpoint.SetMasterVolumeLevelScalar(value / 100.0, None)
    except Exception as exc:
        raise ToolError(f"Could not change system volume: {exc}") from exc
    finally:
        _co_uninit()
    return f"System volume set to {int(round(value))}%."


def _get_volume(ctx: ToolContext) -> dict:
    try:
        endpoint = _com_audio()
        muted = bool(endpoint.GetMute())
        percent = int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
    except Exception as exc:
        raise ToolError(f"Could not read system volume: {exc}") from exc
    finally:
        _co_uninit()
    return {"percent": percent, "muted": muted}


def _set_mute(ctx: ToolContext, mute: bool) -> str:
    try:
        endpoint = _com_audio()
        endpoint.SetMute(bool(mute), None)
    except Exception as exc:
        raise ToolError(f"Could not change mute state: {exc}") from exc
    finally:
        _co_uninit()
    return "Muted." if mute else "Unmuted."


# ----------------------------------------------------------------------- media
def _media(ctx: ToolContext, action: str) -> str:
    return media_key(action)


# ------------------------------------------------------------------- brightness
def _brightness(ctx: ToolContext, percent: int | None = None) -> str:
    try:
        import screen_brightness_control as sbc

        if percent is None:
            values = sbc.get_brightness()
            return f"Display brightness: {values[0]}%."
        sbc.set_brightness(int(clamp(percent, 0, 100)))
        return f"Display brightness set to {int(clamp(percent, 0, 100))}%."
    except Exception as exc:
        raise ToolError(f"Could not change display brightness: {exc}") from exc


# ---------------------------------------------------------------------- status
def _system_status(ctx: ToolContext) -> dict:
    cpu = psutil.cpu_percent(interval=0.35)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    battery: dict | None = None
    try:
        battery_info = psutil.sensors_battery()
        if battery_info:
            battery = {
                "percent": int(battery_info.percent),
                "plugged": bool(battery_info.power_plugged),
                "minutes_left": int(battery_info.secsleft / 60) if battery_info.secsleft > 0 else None,
            }
    except Exception:
        battery = None

    top = []
    for proc in sorted(psutil.process_iter(["name", "memory_info"]), key=lambda p: -(p.info["memory_info"].rss if p.info.get("memory_info") else 0))[:3]:
        top.append({"name": proc.info["name"], "mb": round(proc.info["memory_info"].rss / 1048576, 1)})

    return {
        "cpu_percent": cpu,
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_percent": memory.percent,
        "memory_used_gb": round(memory.used / 1024**3, 2),
        "memory_total_gb": round(memory.total / 1024**3, 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "battery": battery,
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
        "top_memory": top,
        "platform": f"{platform.system()} {platform.release()}",
        "admin": is_admin(),
    }


# ----------------------------------------------------------------------- power
def _lock_session(ctx: ToolContext) -> str:
    if ctypes.windll is None:  # pragma: no cover
        raise ToolError("Not supported on this platform")
    ctypes.windll.user32.LockWorkStation()
    return "Workstation locked."


def _sleep_pc(ctx: ToolContext) -> str:
    if ctypes.windll is None:  # pragma: no cover
        raise ToolError("Not supported on this platform")
    ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
    return "Requested sleep."


def _power(ctx: ToolContext, action: str) -> str:
    action = action.lower()
    flags = {"shutdown": "/s", "restart": "/r", "signout": "/l"}
    if action not in flags:
        raise ToolError(f"Unknown power action '{action}'")
    if shutil.which("shutdown") is None:
        raise ToolError("Windows shutdown command not available")
    import subprocess

    subprocess.run(
        ["shutdown", flags[action], "/t", "0"],
        check=False,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    return f"Requested {action}."


def _settings(ctx: ToolContext, page: str) -> str:
    page = page.strip()
    if not page:
        raise ToolError("Provide a settings page such as 'display', 'sound', 'bluetooth'.")
    os.startfile(f"ms-settings:{page}")
    return f"Opened Settings > {page}."


def _empty_recycle_bin(ctx: ToolContext) -> str:
    if ctypes.windll is None:  # pragma: no cover
        raise ToolError("Not supported on this platform")
    result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x01 | 0x02 | 0x04)
    if result != 0:
        raise ToolError(f"Could not empty the Recycle Bin (code {result}).")
    return "Recycle Bin emptied."


# ----------------------------------------------------------------------- specs
def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="get_volume",
            description="Read the current system volume level and mute state.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_get_volume,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="set_volume",
            description="Set the system volume (0-100) or adjust it by a relative step.",
            parameters={
                "type": "object",
                "properties": {
                    "percent": {"type": "number", "minimum": 0, "maximum": 100},
                    "step": {"type": "integer", "minimum": -100, "maximum": 100},
                },
                "additionalProperties": False,
            },
            handler=_set_volume,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="set_mute",
            description="Mute or unmute system audio.",
            parameters={
                "type": "object",
                "properties": {"mute": {"type": "boolean"}},
                "required": ["mute"],
                "additionalProperties": False,
            },
            handler=_set_mute,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="media_control",
            description="Control media playback: playpause, next, prev, stop, mute, volumeup, volumedown.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["playpause", "next", "prev", "stop", "mute", "volumeup", "volumedown"],
                    }
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=_media,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="set_brightness",
            description="Get or set display brightness (0-100).",
            parameters={
                "type": "object",
                "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
                "additionalProperties": False,
            },
            handler=_brightness,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="get_system_status",
            description="CPU, RAM, disk, battery, uptime and top memory processes.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_system_status,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="lock_workstation",
            description="Lock the Windows session immediately.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_lock_session,
            risk=Risk.MEDIUM,
            category="power",
        ),
        ToolSpec(
            name="sleep_pc",
            description="Put the computer to sleep.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_sleep_pc,
            risk=Risk.MEDIUM,
            category="power",
        ),
        ToolSpec(
            name="power_action",
            description="Shut down, restart or sign out. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"action": {"type": "string", "enum": ["shutdown", "restart", "signout"]}},
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=_power,
            risk=Risk.HIGH,
            category="power",
        ),
        ToolSpec(
            name="open_settings",
            description="Open a Windows Settings page, e.g. display, sound, bluetooth, personalization.",
            parameters={
                "type": "object",
                "properties": {"page": {"type": "string"}},
                "required": ["page"],
                "additionalProperties": False,
            },
            handler=_settings,
            risk=Risk.LOW,
            category="system",
        ),
        ToolSpec(
            name="empty_recycle_bin",
            description="Permanently empty the Recycle Bin. Requires explicit confirmation.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_empty_recycle_bin,
            risk=Risk.HIGH,
            category="system",
        ),
    ]