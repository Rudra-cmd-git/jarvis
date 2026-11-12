"""Screen capture and optional vision analysis.

Capture happens only when the user explicitly asks for it, and the file is saved
under the app data folder so it can be inspected and deleted.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jarvis.core.errors import ToolError
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec
from jarvis.tools.winutil import find_windows, window_rect

logger = logging.getLogger("jarvis.tools.screen")


def _save(shot, directory: Path, prefix: str = "screenshot") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{prefix}-{stamp}.png"
    from mss.tools import to_png

    to_png(shot.rgb, shot.size, output=str(path))
    return path


def _capture_screen(ctx: ToolContext, monitor: int = 1, filename: str | None = None) -> dict:
    import mss

    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor < 1 or monitor >= len(monitors):
            raise ToolError(f"Monitor {monitor} is not available (found {len(monitors) - 1}).")
        shot = sct.grab(monitors[monitor])
    directory = ctx.screenshot_dir()
    if filename:
        path = directory / Path(filename).name
        from mss.tools import to_png

        to_png(shot.rgb, shot.size, output=str(path))
    else:
        path = _save(shot, directory)
    return {
        "path": str(path),
        "width": shot.size[0],
        "height": shot.size[1],
        "monitor": monitor,
    }


def _capture_window(ctx: ToolContext, title: str) -> dict:
    import mss

    matches = find_windows(title)
    if not matches:
        raise ToolError(f"No window matching '{title}'.")
    rect = window_rect(matches[0].hwnd)
    if not rect:
        raise ToolError(f"Could not read the bounds of '{matches[0].title}'.")
    left, top, right, bottom = rect
    region = {
        "left": max(0, left),
        "top": max(0, top),
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }
    with mss.mss() as sct:
        shot = sct.grab(region)
    path = _save(shot, ctx.screenshot_dir(), prefix="window")
    return {
        "path": str(path),
        "window": matches[0].title,
        "width": shot.size[0],
        "height": shot.size[1],
    }


async def _describe_screen(ctx: ToolContext, question: str = "", monitor: int = 1) -> str:
    analyzer = ctx.extra.get("vision_analyze")
    if analyzer is None:
        raise ToolError(
            "Vision analysis is not configured. Add a vision-capable model in Settings > API, "
            "or use capture_screen and open the saved image."
        )
    captured = _capture_screen(ctx, monitor=monitor)
    return await analyzer(question or "Describe what is on the screen and what the user should do next.", captured["path"])


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="capture_screen",
            description="Take a screenshot (only when explicitly requested) and save it to disk.",
            parameters={
                "type": "object",
                "properties": {
                    "monitor": {"type": "integer", "minimum": 1, "maximum": 8},
                    "filename": {"type": "string"},
                },
                "additionalProperties": False,
            },
            handler=_capture_screen,
            risk=Risk.MEDIUM,
            category="screen",
        ),
        ToolSpec(
            name="capture_window",
            description="Screenshot a specific window by title and save it to disk.",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
            handler=_capture_window,
            risk=Risk.MEDIUM,
            category="screen",
        ),
        ToolSpec(
            name="describe_screen",
            description="Capture the screen and ask a vision model to explain it or suggest the next click.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "monitor": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "additionalProperties": False,
            },
            handler=_describe_screen,
            risk=Risk.MEDIUM,
            category="screen",
            timeout=120.0,
        ),
    ]