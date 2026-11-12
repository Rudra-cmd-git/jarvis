"""Reusable automation workflows, stored in the local database."""
from __future__ import annotations

import json
from typing import Any

from jarvis.core.errors import ToolError
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec


def _parse_steps(raw: Any) -> list[dict]:
    if isinstance(raw, str):
        try:
            steps = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolError(f"steps must be a JSON array: {exc}") from exc
    elif isinstance(raw, list):
        steps = raw
    else:
        raise ToolError("steps must be a JSON array of {tool, args} objects.")
    if not steps:
        raise ToolError("A workflow needs at least one step.")
    cleaned = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or "tool" not in step:
            raise ToolError(f"Step {index} must be an object with a 'tool' field.")
        args = step.get("args") or {}
        if not isinstance(args, dict):
            raise ToolError(f"Step {index} 'args' must be an object.")
        cleaned.append({"tool": step["tool"], "args": args})
    return cleaned


def _create_workflow(
    ctx: ToolContext, name: str, steps: str, description: str = ""
) -> dict:
    cleaned = _parse_steps(steps)
    registry = ctx.extra.get("registry")
    if registry is not None:
        for step in cleaned:
            if step["tool"] not in registry.names():
                raise ToolError(f"Unknown tool '{step['tool']}' in workflow '{name}'.")
    saved = ctx.store.save_workflow(name.strip(), description, cleaned)
    return {"name": saved["name"], "steps": len(cleaned), "description": saved.get("description", "")}


def _list_workflows(ctx: ToolContext) -> dict:
    items = [
        {
            "name": w["name"],
            "description": w["description"],
            "steps": len(json.loads(w.get("steps_json") or "[]")),
        }
        for w in ctx.store.list_workflows()
    ]
    return {"count": len(items), "workflows": items}


def _get_workflow(ctx: ToolContext, name: str) -> dict:
    workflow = ctx.store.get_workflow(name)
    if not workflow:
        raise ToolError(f"No workflow named '{name}'.")
    return workflow


def _delete_workflow(ctx: ToolContext, name: str) -> str:
    ctx.store.delete_workflow(name)
    return f"Workflow '{name}' deleted."


async def _run_workflow(ctx: ToolContext, name: str) -> str:
    runner = ctx.extra.get("run_workflow")
    if runner is None:
        raise ToolError("Workflow execution is not available in this context.")
    return await runner(name)


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="create_workflow",
            description=(
                "Save a reusable sequence of tool calls. steps is a JSON array like "
                '[{"tool":"open_app","args":{"name":"chrome"}}]. Requires confirmation.'
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "steps": {"type": "string", "description": "JSON array of {tool, args}"},
                    "description": {"type": "string"},
                },
                "required": ["name", "steps"],
                "additionalProperties": False,
            },
            handler=_create_workflow,
            risk=Risk.MEDIUM,
            category="workflows",
        ),
        ToolSpec(
            name="list_workflows",
            description="List saved workflows.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_list_workflows,
            risk=Risk.LOW,
            category="workflows",
        ),
        ToolSpec(
            name="get_workflow",
            description="Show the steps of a saved workflow.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_get_workflow,
            risk=Risk.LOW,
            category="workflows",
        ),
        ToolSpec(
            name="delete_workflow",
            description="Delete a saved workflow. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_delete_workflow,
            risk=Risk.MEDIUM,
            category="workflows",
        ),
        ToolSpec(
            name="run_workflow",
            description="Run a saved workflow step by step, asking for confirmation where needed.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_run_workflow,
            risk=Risk.MEDIUM,
            category="workflows",
            timeout=300.0,
        ),
    ]