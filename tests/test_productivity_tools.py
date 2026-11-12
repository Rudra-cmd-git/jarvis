import asyncio
from datetime import datetime, timedelta

import pytest

from jarvis.core.errors import ToolError
from jarvis.tools.builtin import build_registry
from jarvis.tools.productivity import parse_when


def _run(coro):
    return asyncio.run(coro)


def test_parse_when_relative() -> None:
    parsed = datetime.fromisoformat(parse_when("in 10 minutes"))
    delta = parsed - datetime.now()
    assert timedelta(minutes=9) < delta < timedelta(minutes=11)


def test_parse_when_clock_and_tomorrow() -> None:
    parsed = datetime.fromisoformat(parse_when("tomorrow at 09:30"))
    assert parsed.hour == 9 and parsed.minute == 30
    assert parsed.date() > datetime.now().date()


def test_parse_when_invalid() -> None:
    with pytest.raises(ToolError):
        parse_when("sometime later")


def test_productivity_tools(ctx) -> None:
    reg = build_registry()
    reminder = _run(reg.execute("create_reminder", {"text": "Call mom", "when": "in 30 minutes"}, ctx))
    assert reminder.ok
    listed = _run(reg.execute("list_reminders", {}, ctx))
    assert listed.output["count"] == 1

    todo = _run(reg.execute("add_todo", {"text": "Ship it"}, ctx))
    assert todo.ok
    assert _run(reg.execute("list_todos", {}, ctx)).output["count"] == 1

    note = _run(reg.execute("create_note", {"title": "Idea", "body": "A small robot"}, ctx))
    assert note.ok
    assert _run(reg.execute("search_notes", {"query": "robot"}, ctx)).output["count"] == 1

    timer = _run(reg.execute("start_timer", {"minutes": 1, "label": "Focus"}, ctx))
    assert timer.ok
    status = _run(reg.execute("timer_status", {}, ctx))
    assert status.output["active"] is True
    cancelled = _run(reg.execute("cancel_timer", {}, ctx))
    assert cancelled.ok
    assert _run(reg.execute("timer_status", {}, ctx)).output["active"] is False

    summary = _run(reg.execute("daily_summary", {}, ctx))
    assert summary.ok
    assert "open_todos" in summary.output


def test_secret_like_note_is_still_saved_but_memory_rejects(ctx) -> None:
    reg = build_registry()
    result = _run(reg.execute("remember", {"content": "my api key is sk-ABCDEFGHIJKLMNOP1234"}, ctx))
    assert result.ok is False
    assert "secret" in result.error.lower() or "password" in result.error.lower()