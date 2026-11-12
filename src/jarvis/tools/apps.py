"""Application discovery and lifecycle tools.

Resolution order: explicit path, alias table, Windows "App Paths" registry,
Start Menu shortcuts, then PATH. Nothing here guesses at coordinates.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import winreg
from pathlib import Path

from jarvis.core.errors import ToolError
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec
from jarvis.tools.winutil import find_windows, force_foreground, launch_program, list_windows

logger = logging.getLogger("jarvis.tools.apps")

ALIASES: dict[str, str] = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "notepad": "notepad.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "wordpad": "write.exe",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
    "vs code": "code.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "steam": "steam.exe",
    "vlc": "vlc.exe",
    "obs": "obs64.exe",
}

_START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "Microsoft/Windows/Start Menu/Programs",
]
_index_cache: dict[str, str] | None = None


def _normalise(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()


class AppIndex:
    def __init__(self) -> None:
        self._cache: dict[str, str] | None = None

    # ---------------------------------------------------------------- discovery
    def _build(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for name, exe in ALIASES.items():
            index[_normalise(name)] = exe

        # 1) App Paths registry (authoritative for installed programs)
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            try:
                with winreg.OpenKey(hive, base) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        sub_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, sub_name) as sub:
                                default, _ = winreg.QueryValueEx(sub, "")
                        except OSError:
                            continue
                        if default and os.path.exists(default):
                            index.setdefault(_normalise(Path(sub_name).stem), default)
            except OSError:
                pass

        # 2) Start Menu shortcuts
        for directory in _START_MENU_DIRS:
            if not directory.exists():
                continue
            for root, _dirs, files in os.walk(directory):
                for file_name in files:
                    if not file_name.lower().endswith(".lnk"):
                        continue
                    stem = Path(file_name).stem
                    index.setdefault(_normalise(stem), str(Path(root) / file_name))

        # 3) PATH executables
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir:
                continue
            try:
                for entry in os.listdir(path_dir):
                    if entry.lower().endswith(".exe"):
                        index.setdefault(_normalise(Path(entry).stem), str(Path(path_dir) / entry))
            except OSError:
                continue
        return index

    def _ensure(self) -> dict[str, str]:
        if self._cache is None:
            self._cache = self._build()
        return self._cache

    def resolve(self, name: str) -> list[str]:
        if not name:
            return []
        raw = name.strip()
        candidates: list[str] = []

        def add(value: str | None) -> None:
            if value and value not in candidates:
                candidates.append(value)

        if os.path.sep in raw or raw.lower().endswith((".exe", ".lnk", ".bat", ".cmd")):
            add(raw)
        add(ALIASES.get(raw.lower()))
        index = self._ensure()
        add(index.get(_normalise(raw)))
        for key, value in index.items():
            if raw.lower() in key:
                add(value)
        add(shutil.which(raw))
        add(shutil.which(f"{raw}.exe"))
        return candidates

    def find(self, name: str) -> str:
        candidates = self.resolve(name)
        for candidate in candidates:
            if candidate.lower().startswith("ms-settings:"):
                return candidate
            if os.path.exists(candidate):
                return candidate
        raise ToolError(
            f"Could not find an application matching '{name}'. "
            "Install it, or provide the full path to the executable."
        )

    def refresh(self) -> None:
        self._cache = None


_INDEX: AppIndex | None = None


def app_index() -> AppIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = AppIndex()
    return _INDEX


# ----------------------------------------------------------------------- tools
def _open_app(ctx: ToolContext, name: str, arguments: str | None = None) -> str:
    executable = app_index().find(name)
    if executable.lower().startswith("ms-settings:"):
        os.startfile(executable)
        return f"Opened Windows Settings ({executable.split(':', 1)[1]})."
    args = [a for a in (arguments or "").split() if a]
    expected = Path(executable).name.lower()
    if executable.lower().endswith(".lnk"):
        target = _shortcut_target(executable)
        if target:
            expected = Path(target).name.lower()
    pid = launch_program(executable, args)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if pid and _pid_alive(pid):
            return f"Opened '{expected}' (PID {pid})."
        if _process_running(expected):
            return f"Opened '{expected}'."
        time.sleep(0.4)
    return f"Launch command sent for '{expected}', but no matching process was detected yet."


def _pid_alive(pid: int) -> bool:
    import psutil

    try:
        return psutil.Process(pid).is_running()
    except Exception:
        return False


def _shortcut_target(lnk_path: str) -> str | None:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            return shell.CreateShortcut(lnk_path).Targetpath
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        logger.exception("Could not read shortcut %s", lnk_path)
        return None


def _process_running(exe_name: str) -> bool:
    import psutil

    target = exe_name.lower()
    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == target:
            return True
    return False


def _list_running_apps(ctx: ToolContext) -> list[dict]:
    windows = list_windows()
    seen: dict[int, dict] = {}
    for window in windows:
        if window.pid in seen:
            continue
        seen[window.pid] = {
            "process": window.process,
            "pid": window.pid,
            "window": window.title,
            "minimized": window.minimized,
            "active": window.active,
        }
    return sorted(seen.values(), key=lambda item: item["process"].lower())


def _switch_app(ctx: ToolContext, name: str) -> str:
    matches = find_windows(name)
    if not matches:
        raise ToolError(f"No open window matches '{name}'. Open it first.")
    exact = [w for w in matches if w.title.lower() == name.lower()]
    target = (exact or matches)[0]
    if not force_foreground(target.hwnd):
        raise ToolError(f"Found '{target.title}' but Windows refused to bring it to the foreground.")
    return f"Switched to '{target.title}' ({target.process})."


def _close_app(ctx: ToolContext, name: str) -> str:
    import psutil

    from jarvis.tools.winutil import processes_matching

    procs = processes_matching(name)
    if not procs:
        raise ToolError(f"'{name}' does not appear to be running.")
    closed = []
    for proc in procs:
        try:
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except Exception:
                    pass
            proc.terminate()
            proc.wait(timeout=4)
            closed.append(proc.pid)
        except psutil.NoSuchProcess:
            continue
        except Exception:
            try:
                proc.kill()
                closed.append(proc.pid)
            except Exception:
                pass
    if not closed:
        raise ToolError(f"Could not close '{name}'.")
    return f"Closed '{name}' (PID {', '.join(str(p) for p in closed)})."


def _close_window(ctx: ToolContext, title: str) -> str:
    import win32gui
    import win32con

    matches = find_windows(title)
    if not matches:
        raise ToolError(f"No window matching '{title}'.")
    target = matches[0]
    win32gui.PostMessage(target.hwnd, win32con.WM_CLOSE, 0, 0)
    return f"Sent a close request to '{target.title}'."


def _focus_window(ctx: ToolContext, title: str) -> str:
    return _switch_app(ctx, title)


def _window_state(ctx: ToolContext, title: str, action: str) -> str:
    import win32con
    import win32gui

    matches = find_windows(title)
    if not matches:
        raise ToolError(f"No window matching '{title}'.")
    target = matches[0]
    if action == "minimize":
        win32gui.ShowWindow(target.hwnd, win32con.SW_MINIMIZE)
    elif action == "maximize":
        win32gui.ShowWindow(target.hwnd, win32con.SW_MAXIMIZE)
    elif action == "restore":
        win32gui.ShowWindow(target.hwnd, win32con.SW_RESTORE)
    else:
        raise ToolError(f"Unknown window action '{action}'")
    return f"{action.capitalize()}d '{target.title}'."


def _active_window_info(ctx: ToolContext) -> dict:
    from jarvis.tools.winutil import active_window

    window = active_window()
    if window is None:
        return {"active": False, "title": ""}
    return {"active": True, **window.as_dict()}


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="open_app",
            description="Launch an application by name or full path. Verifies the process started.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name, e.g. 'chrome' or 'notepad'"},
                    "arguments": {"type": "string", "description": "Optional launch arguments"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_open_app,
            risk=Risk.LOW,
            category="applications",
        ),
        ToolSpec(
            name="list_running_apps",
            description="List currently running apps with window titles and process IDs.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_list_running_apps,
            risk=Risk.LOW,
            category="applications",
        ),
        ToolSpec(
            name="switch_app",
            description="Bring an already-open application window to the foreground.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Window title or process name"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_switch_app,
            risk=Risk.LOW,
            category="applications",
        ),
        ToolSpec(
            name="close_app",
            description="Terminate an application by process name. Unsaved work may be lost.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_close_app,
            risk=Risk.MEDIUM,
            category="applications",
        ),
        ToolSpec(
            name="focus_window",
            description="Focus a window whose title contains the given text.",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
            handler=_focus_window,
            risk=Risk.LOW,
            category="windows",
        ),
        ToolSpec(
            name="close_window",
            description="Ask the window matching a title to close (like clicking the X).",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
            handler=_close_window,
            risk=Risk.MEDIUM,
            category="windows",
        ),
        ToolSpec(
            name="set_window_state",
            description="Minimize, maximize or restore a window by title.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "action": {"type": "string", "enum": ["minimize", "maximize", "restore"]},
                },
                "required": ["title", "action"],
                "additionalProperties": False,
            },
            handler=_window_state,
            risk=Risk.LOW,
            category="windows",
        ),
        ToolSpec(
            name="get_active_window",
            description="Return the title and process of the currently focused window.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_active_window_info,
            risk=Risk.LOW,
            category="windows",
        ),
    ]