import asyncio

from jarvis.tools.apps import app_index
from jarvis.tools.builtin import build_registry
from jarvis.tools.system import _system_status
from jarvis.tools.web import _normalise_url
from jarvis.core.errors import ToolError
import pytest


def test_app_index_resolves_notepad() -> None:
    path = app_index().find("notepad")
    assert path
    assert path.lower().endswith(".exe") or path.lower().startswith("ms-settings:")


def test_system_status_shape(ctx) -> None:
    data = _system_status(ctx)
    for key in ("cpu_percent", "memory_percent", "disk_percent", "uptime_hours", "platform"):
        assert key in data


def test_volume_and_clipboard_roundtrip(ctx) -> None:
    from jarvis.tools.clipboard import _read_clipboard, _write_clipboard

    _write_clipboard(ctx, "clip test 123")
    assert "clip test 123" in _read_clipboard(ctx)


def test_url_validation() -> None:
    assert _normalise_url("example.com").startswith("https://")
    with pytest.raises(ToolError):
        _normalise_url("ftp://example.com/file")
    with pytest.raises(ToolError):
        _normalise_url("")


def test_screen_capture(ctx) -> None:
    reg = build_registry()
    result = asyncio.run(reg.execute("capture_screen", {}, ctx))
    assert result.ok, result.error
    from pathlib import Path

    assert Path(result.output["path"]).exists()


def test_read_clipboard_empty_is_safe(ctx) -> None:
    reg = build_registry()
    result = asyncio.run(reg.execute("read_clipboard", {"max_chars": 100}, ctx))
    assert result.ok
    assert isinstance(result.output, str)