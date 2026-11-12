"""User-controlled long-term memory tools.

Secrets are rejected by the store; memory can be disabled in settings, in which
case these tools report that fact instead of silently doing nothing.
"""
from __future__ import annotations

from jarvis.core.errors import ToolError
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec


def _guard(ctx: ToolContext) -> None:
    if not ctx.config.memory_enabled:
        raise ToolError(
            "Memory is disabled. Enable it in Settings > Memory to let JARVIS remember preferences."
        )


def _remember(ctx: ToolContext, content: str, kind: str = "fact") -> dict:
    _guard(ctx)
    try:
        return ctx.store.add_memory(content, kind=kind, source="assistant")
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def _recall(ctx: ToolContext, query: str = "", limit: int = 10) -> dict:
    _guard(ctx)
    items = ctx.store.list_memories(limit=200)
    if query.strip():
        needle = query.strip().lower()
        items = [item for item in items if needle in item["content"].lower()]
    return {"count": len(items[:limit]), "memories": items[:limit]}


def _list_memory(ctx: ToolContext) -> dict:
    _guard(ctx)
    items = ctx.store.list_memories()
    return {"count": len(items), "memories": items, "enabled": True}


def _forget(ctx: ToolContext, query: str) -> str:
    _guard(ctx)
    needle = query.strip().lower()
    if not needle:
        raise ToolError("Provide the text to forget.")
    items = ctx.store.list_memories(limit=500)
    matches = [item for item in items if needle in item["content"].lower()]
    if not matches:
        return f"No stored memory matched '{query}'."
    for item in matches:
        ctx.store.delete_memory(item["id"])
    return f"Deleted {len(matches)} matching memory entr{'y' if len(matches) == 1 else 'ies'}."


def _update_memory(ctx: ToolContext, memory_id: str, content: str) -> str:
    _guard(ctx)
    try:
        ctx.store.update_memory(memory_id, content)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return f"Updated memory {memory_id}."


def _clear_memory(ctx: ToolContext) -> str:
    _guard(ctx)
    count = len(ctx.store.list_memories(limit=1000))
    ctx.store.clear_memories()
    return f"Cleared {count} memory entries."


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="remember",
            description="Save a user-approved fact or preference to long-term memory. Never store secrets.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["fact", "preference", "project", "workflow"],
                    },
                },
                "required": ["content"],
                "additionalProperties": False,
            },
            handler=_remember,
            risk=Risk.LOW,
            category="memory",
        ),
        ToolSpec(
            name="recall",
            description="Search long-term memory for stored facts and preferences.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
            handler=_recall,
            risk=Risk.LOW,
            category="memory",
        ),
        ToolSpec(
            name="list_memory",
            description="Show everything JARVIS remembers.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_list_memory,
            risk=Risk.LOW,
            category="memory",
        ),
        ToolSpec(
            name="forget",
            description="Delete stored memories matching a phrase. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_forget,
            risk=Risk.MEDIUM,
            category="memory",
        ),
        ToolSpec(
            name="update_memory",
            description="Replace the text of a stored memory by id.",
            parameters={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}, "content": {"type": "string"}},
                "required": ["memory_id", "content"],
                "additionalProperties": False,
            },
            handler=_update_memory,
            risk=Risk.MEDIUM,
            category="memory",
        ),
        ToolSpec(
            name="clear_memory",
            description="Delete every stored memory. Requires confirmation.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_clear_memory,
            risk=Risk.HIGH,
            category="memory",
        ),
    ]