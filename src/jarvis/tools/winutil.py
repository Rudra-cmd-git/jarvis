"""Thin, dependency-light wrappers around Win32 for windows, keys and process info.

Everything here prefers stable Windows APIs over screen-coordinate automation.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

logger = logging.getLogger("jarvis.tools.winutil")

try:  # pragma: no cover - import guard for non-Windows test runs
    import win32api
    import win32clipboard
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32api = win32clipboard = win32con = win32gui = win32process = None  # type: ignore


# --------------------------------------------------------------------- windows
@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    process: str
    class_name: str
    minimized: bool
    active: bool

    def as_dict(self) -> dict:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "pid": self.pid,
            "process": self.process,
            "class": self.class_name,
            "minimized": self.minimized,
            "active": self.active,
        }


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def list_windows() -> list[WindowInfo]:
    if win32gui is None:
        return []
    results: list[WindowInfo] = []

    def callback(hwnd: int, _payload: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if not title.strip():
            return True
        class_name = win32gui.GetClassName(hwnd) or ""
        if class_name in {"Shell_TrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow"}:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        results.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                pid=pid,
                process=_process_name(pid),
                class_name=class_name,
                minimized=bool(win32gui.IsIconic(hwnd)),
                active=win32gui.GetForegroundWindow() == hwnd,
            )
        )
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:  # pragma: no cover
        logger.exception("EnumWindows failed")
    return results


def find_windows(needle: str) -> list[WindowInfo]:
    needle = (needle or "").lower()
    return [w for w in list_windows() if needle in w.title.lower() or needle in w.process.lower()]


def active_window() -> WindowInfo | None:
    windows = list_windows()
    return next((w for w in windows if w.active), None)


def force_foreground(hwnd: int) -> bool:
    if win32gui is None:
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        fg_thread, _ = win32process.GetWindowThreadProcessId(fg)
        current_thread = win32api.GetCurrentThreadId()
        win32process.AttachThreadInput(current_thread, fg_thread, True)
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd)
        finally:
            win32process.AttachThreadInput(current_thread, fg_thread, False)
        time.sleep(0.08)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        logger.exception("Could not focus window %s", hwnd)
        return False


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if win32gui is None:
        return None
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


# ---------------------------------------------------------------------- inputs
_VK = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "printscreen": 0x2C,
    "capslock": 0x14,
    "win": 0x5B,
    "super": 0x5B,
    "meta": 0x5B,
}
for _i in range(1, 13):
    _VK[f"f{_i}"] = 0x70 + _i - 1
for _ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    _VK[_ch] = ord(_ch.upper())

_MODIFIERS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}

_MEDIA_VK = {
    "playpause": 0xB3,
    "play": 0xB3,
    "pause": 0xB3,
    "next": 0xB0,
    "nexttrack": 0xB0,
    "prev": 0xB1,
    "previous": 0xB1,
    "prevtrack": 0xB1,
    "stop": 0xB2,
    "mute": 0xAD,
    "volumeup": 0xAF,
    "volumedown": 0xAE,
}


def _key_event(vk: int, up: bool = False) -> None:
    if win32api is None:
        return
    win32api.keybd_event(vk, 0, 0x0002 if up else 0, 0)


def press_keys(keys: str) -> str:
    """Press a combo such as 'ctrl+shift+esc' or a single key like 'enter'."""
    if win32api is None:
        raise RuntimeError("Keyboard control requires Windows")
    parts = [p.strip().lower() for p in str(keys).split("+") if p.strip()]
    if not parts:
        return "No keys provided"
    codes: list[int] = []
    modifiers: list[int] = []
    for part in parts:
        if part in _MODIFIERS:
            modifiers.append(_MODIFIERS[part])
        elif part in _VK:
            codes.append(_VK[part])
        else:
            raise ValueError(f"Unknown key '{part}'")
    for vk in modifiers:
        _key_event(vk)
    try:
        for vk in codes:
            _key_event(vk)
            time.sleep(0.02)
            _key_event(vk, up=True)
            time.sleep(0.02)
    finally:
        for vk in reversed(modifiers):
            _key_event(vk, up=True)
    return f"Pressed {'+'.join(parts)}"


def media_key(action: str) -> str:
    action = action.lower().strip()
    vk = _MEDIA_VK.get(action)
    if vk is None:
        raise ValueError(f"Unknown media action '{action}'")
    _key_event(vk)
    time.sleep(0.02)
    _key_event(vk, up=True)
    return f"Sent media key {action}"


def type_unicode(text: str) -> str:
    """Type text into the focused window using the clipboard (reliable for Unicode)."""
    previous = read_clipboard() or ""
    write_clipboard(text)
    try:
        press_keys("ctrl+v")
        time.sleep(0.15)
        return f"Typed {len(text)} characters into the active window."
    finally:
        # Restore the old clipboard shortly after the paste lands.
        def restore() -> None:
            time.sleep(1.2)
            try:
                write_clipboard(previous)
            except Exception:  # pragma: no cover
                pass

        import threading

        threading.Thread(target=restore, daemon=True).start()


# ------------------------------------------------------------------- clipboard
def read_clipboard() -> str:
    if win32clipboard is None:
        return ""
    try:
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return ""
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return ""


def write_clipboard(text: str) -> None:
    if win32clipboard is None:
        raise RuntimeError("Clipboard requires Windows")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text))
    finally:
        win32clipboard.CloseClipboard()


# --------------------------------------------------------------------- process
def processes_matching(name: str) -> list[psutil.Process]:
    needle = name.strip().lower().removesuffix(".exe")
    matches: list[psutil.Process] = []
    for proc in psutil.process_iter(["name", "exe"]):
        proc_name = (proc.info.get("name") or "").lower()
        exe = (proc.info.get("exe") or "").lower()
        if proc_name == f"{needle}.exe" or Path(exe).name == f"{needle}.exe":
            matches.append(proc)
    return matches


def exe_candidates(name: str) -> list[str]:
    from jarvis.tools.apps import app_index

    return app_index().resolve(name)


def launch_program(exe: str, args: Iterable[str] | None = None, cwd: str | None = None) -> int:
    if not os.path.exists(exe):
        raise FileNotFoundError(exe)
    creation = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    if str(exe).lower().endswith(".lnk"):
        os.startfile(exe)  # ShellExecute handles shortcuts, UWP and installers
        return 0
    proc = subprocess.Popen(
        [exe, *(args or [])],
        cwd=cwd or str(Path(exe).parent),
        creationflags=creation,
        close_fds=True,
    )
    return proc.pid


def is_admin() -> bool:
    if ctypes.windll is None:  # pragma: no cover
        return False
    return bool(ctypes.windll.shell32.IsUserAnAdmin())