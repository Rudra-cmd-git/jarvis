"""Clipboard access tools."""
from __future__ import annotations

from jarvis.core.util import truncate
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec
from jarvis.tools.winutil import read_clipboard as _read
from jarvis.tools.winutil import write_clipboard as _write


def _read_clipboard(ctx: ToolContext, max_chars: int = 5000) -> str:
    text = _read()
    if not text:
        return "The clipboard is empty or does not contain text."
    return truncate(text, max(50, min(max_chars, 50000)))


def _write_clipboard(ctx: ToolContext, text: str) -> str:
    _write(text)
    return f"Copied {len(text)} characters to the clipboard."


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="read_clipboard",
            description="Read the current clipboard text.",
            parameters={
                "type": "object",
                "properties": {"max_chars": {"type": "integer", "minimum": 50, "maximum": 50000}},
                "additionalProperties": False,
            },
            handler=_read_clipboard,
            risk=Risk.LOW,
            category="clipboard",
        ),
        ToolSpec(
            name="write_clipboard",
            description="Replace the clipboard contents with the given text.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=_write_clipboard,
            risk=Risk.MEDIUM,
            category="clipboard",
        ),
    ]