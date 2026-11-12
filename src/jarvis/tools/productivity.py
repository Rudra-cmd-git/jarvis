"""Productivity tools: reminders, to-dos, notes, study timer and daily summary."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from jarvis.core.errors import ToolError
from jarvis.core.util import now_iso, truncate
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_when(text: str) -> str:
    """Parse a small, predictable subset of natural time expressions."""
    raw = (text or "").strip()
    if not raw:
        raise ToolError("Provide a time, e.g. 'in 10 minutes' or 'at 18:30'.")
    value = raw.lower()

    try:
        return datetime.fromisoformat(value).isoformat(timespec="seconds")
    except ValueError:
        pass

    relative = re.match(r"^in\s+(\d+)\s+(second|minute|hour|day)s?(?:\s+)?(.*)$", value)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        return (datetime.now() + timedelta(seconds=amount * _UNIT_SECONDS[unit])).isoformat(
            timespec="seconds"
        )

    tomorrow = value.startswith("tomorrow")
    clock = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", value)
    if clock:
        hour = int(clock.group(1))
        minute = int(clock.group(2))
        meridiem = clock.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            raise ToolError(f"'{raw}' is not a valid time of day.")
        target_date = datetime.now() + timedelta(days=1) if tomorrow else datetime.now()
        moment = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if moment <= datetime.now() and not tomorrow:
            moment += timedelta(days=1)
        return moment.isoformat(timespec="seconds")

    raise ToolError(
        f"Could not understand the time '{raw}'. Try 'in 15 minutes', 'at 18:30' or an ISO timestamp."
    )


def _reminder_due(text: str) -> str:
    return parse_when(text)


def _create_reminder(ctx: ToolContext, text: str, when: str) -> dict:
    due = _reminder_due(when)
    return ctx.store.add_reminder(text, due)


def _list_reminders(ctx: ToolContext, include_done: bool = False) -> dict:
    items = ctx.store.list_reminders(include_done=include_done)
    return {"count": len(items), "reminders": items, "now": now_iso()}


def _complete_reminder(ctx: ToolContext, reminder_id: str) -> str:
    ctx.store.complete_reminder(reminder_id)
    return f"Reminder {reminder_id} marked done."


def _delete_reminder(ctx: ToolContext, reminder_id: str) -> str:
    ctx.store.delete_reminder(reminder_id)
    return f"Reminder {reminder_id} deleted."


def _add_todo(ctx: ToolContext, text: str, due: str | None = None) -> dict:
    due_at = parse_when(due) if due else None
    return ctx.store.add_todo(text, due_at)


def _list_todos(ctx: ToolContext, include_done: bool = True) -> dict:
    items = ctx.store.list_todos(include_done=include_done)
    return {"count": len(items), "todos": items}


def _complete_todo(ctx: ToolContext, todo_id: str, done: bool = True) -> str:
    ctx.store.complete_todo(todo_id, done)
    return f"To-do {todo_id} marked {'done' if done else 'not done'}."


def _delete_todo(ctx: ToolContext, todo_id: str) -> str:
    ctx.store.delete_todo(todo_id)
    return f"To-do {todo_id} deleted."


def _create_note(ctx: ToolContext, title: str, body: str) -> dict:
    entry = ctx.store.add_note(title, body)
    return {"id": entry["id"], "title": entry["title"], "created_at": entry["created_at"]}


def _list_notes(ctx: ToolContext, limit: int = 50) -> dict:
    items = [
        {"id": n["id"], "title": n["title"], "updated_at": n["updated_at"], "preview": truncate(n["body"], 120)}
        for n in ctx.store.list_notes(limit)
    ]
    return {"count": len(items), "notes": items}


def _search_notes(ctx: ToolContext, query: str) -> dict:
    items = [
        {"id": n["id"], "title": n["title"], "body": truncate(n["body"], 800)}
        for n in ctx.store.search_notes(query)
    ]
    return {"count": len(items), "notes": items}


def _read_note(ctx: ToolContext, note_id: str) -> dict:
    note = ctx.store.get_note(note_id)
    if not note:
        raise ToolError(f"No note with id {note_id}.")
    return note


def _delete_note(ctx: ToolContext, note_id: str) -> str:
    ctx.store.delete_note(note_id)
    return f"Note {note_id} deleted."


def _start_timer(ctx: ToolContext, minutes: float, label: str = "Timer") -> dict:
    if minutes <= 0 or minutes > 600:
        raise ToolError("Timer length must be between 0 and 600 minutes.")
    entry = ctx.store.start_timer(label, int(minutes * 60))
    ctx.ui.notify("Timer started", f"{label} — {minutes:g} minutes", "info")
    return entry


def _timer_status(ctx: ToolContext) -> dict:
    timer = ctx.store.active_timer()
    if not timer:
        return {"active": False}
    ends = datetime.fromisoformat(timer["ends_at"])
    remaining = (ends - datetime.now()).total_seconds()
    if remaining <= 0:
        ctx.store.complete_timer(timer["id"])
        ctx.ui.notify("Timer finished", timer["label"], "success")
        return {"active": False, "finished": timer["label"], "timer_id": timer["id"]}
    return {
        "active": True,
        "label": timer["label"],
        "remaining_seconds": int(remaining),
        "ends_at": timer["ends_at"],
        "timer_id": timer["id"],
    }


def _cancel_timer(ctx: ToolContext) -> str:
    timer = ctx.store.active_timer()
    if not timer:
        return "No active timer."
    ctx.store.stop_timer(timer["id"])
    return f"Timer '{timer['label']}' cancelled."


def _daily_summary(ctx: ToolContext) -> dict:
    todos = ctx.store.list_todos()
    reminders = ctx.store.list_reminders()
    actions = ctx.store.recent_actions(limit=15)
    return {
        "date": datetime.now().strftime("%A, %d %B %Y"),
        "open_todos": [t["text"] for t in todos if not t["done"]],
        "done_todos": [t["text"] for t in todos if t["done"]],
        "upcoming_reminders": [
            {"text": r["text"], "due_at": r["due_at"]} for r in reminders if not r["done"]
        ],
        "recent_actions": [
            {"tool": a["tool"], "ok": bool(a["ok"]), "at": a["created_at"], "summary": a["summary"]}
            for a in actions[:10]
        ],
    }


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="create_reminder",
            description="Create a reminder at a specific time. Accepts 'in 20 minutes' or 'at 18:30'.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "when": {"type": "string", "description": "e.g. 'in 20 minutes', 'tomorrow at 09:00'"},
                },
                "required": ["text", "when"],
                "additionalProperties": False,
            },
            handler=_create_reminder,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="list_reminders",
            description="List pending reminders.",
            parameters={
                "type": "object",
                "properties": {"include_done": {"type": "boolean"}},
                "additionalProperties": False,
            },
            handler=_list_reminders,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="complete_reminder",
            description="Mark a reminder as done.",
            parameters={
                "type": "object",
                "properties": {"reminder_id": {"type": "string"}},
                "required": ["reminder_id"],
                "additionalProperties": False,
            },
            handler=_complete_reminder,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="delete_reminder",
            description="Delete a reminder.",
            parameters={
                "type": "object",
                "properties": {"reminder_id": {"type": "string"}},
                "required": ["reminder_id"],
                "additionalProperties": False,
            },
            handler=_delete_reminder,
            risk=Risk.MEDIUM,
            category="productivity",
        ),
        ToolSpec(
            name="add_todo",
            description="Add a task to the to-do list.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=_add_todo,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="list_todos",
            description="List to-dos.",
            parameters={
                "type": "object",
                "properties": {"include_done": {"type": "boolean"}},
                "additionalProperties": False,
            },
            handler=_list_todos,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="complete_todo",
            description="Mark a to-do as done or not done.",
            parameters={
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string"},
                    "done": {"type": "boolean"},
                },
                "required": ["todo_id"],
                "additionalProperties": False,
            },
            handler=_complete_todo,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="delete_todo",
            description="Delete a to-do.",
            parameters={
                "type": "object",
                "properties": {"todo_id": {"type": "string"}},
                "required": ["todo_id"],
                "additionalProperties": False,
            },
            handler=_delete_todo,
            risk=Risk.MEDIUM,
            category="productivity",
        ),
        ToolSpec(
            name="create_note",
            description="Save a quick note.",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
            handler=_create_note,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="list_notes",
            description="List saved notes.",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
                "additionalProperties": False,
            },
            handler=_list_notes,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="search_notes",
            description="Search saved notes by text.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_search_notes,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="read_note",
            description="Read a saved note by id.",
            parameters={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
                "additionalProperties": False,
            },
            handler=_read_note,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="delete_note",
            description="Delete a saved note.",
            parameters={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
                "additionalProperties": False,
            },
            handler=_delete_note,
            risk=Risk.MEDIUM,
            category="productivity",
        ),
        ToolSpec(
            name="start_timer",
            description="Start a study/focus timer in minutes.",
            parameters={
                "type": "object",
                "properties": {
                    "minutes": {"type": "number", "minimum": 0.1, "maximum": 600},
                    "label": {"type": "string"},
                },
                "required": ["minutes"],
                "additionalProperties": False,
            },
            handler=_start_timer,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="timer_status",
            description="Show the remaining time on the active timer.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_timer_status,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="cancel_timer",
            description="Cancel the active timer.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_cancel_timer,
            risk=Risk.LOW,
            category="productivity",
        ),
        ToolSpec(
            name="daily_summary",
            description="Summarize today's open tasks, reminders and recent JARVIS actions.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_daily_summary,
            risk=Risk.LOW,
            category="productivity",
        ),
    ]