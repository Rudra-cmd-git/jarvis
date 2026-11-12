import asyncio
from pathlib import Path

from jarvis.automation.controller import AutomationController
from jarvis.core.errors import ToolError
from jarvis.tools.builtin import build_registry


def test_workflow_runs_steps(ctx) -> None:
    registry = build_registry()
    policy = ctx.policy
    automation = AutomationController(registry, policy, ctx.ui, ctx.store)
    ctx.extra["registry"] = registry

    steps = [
        {"tool": "create_file", "args": {"path": str(Path(ctx.config.allowed_roots[0]) / "w.txt"), "content": "from workflow"}},
        {"tool": "add_todo", "args": {"text": "workflow todo"}},
    ]
    ctx.store.save_workflow("Demo", "demo", steps)

    result = asyncio.run(automation.run_workflow("Demo", ctx))
    assert "2/2" in result
    assert (Path(ctx.config.allowed_roots[0]) / "w.txt").exists()
    assert ctx.store.list_todos()[0]["text"] == "workflow todo"


def test_workflow_with_unknown_tool_reports_failure(ctx) -> None:
    registry = build_registry()
    automation = AutomationController(registry, ctx.policy, ctx.ui, ctx.store)
    ctx.store.save_workflow("Broken", "", [{"tool": "no_such_tool", "args": {}}])
    try:
        asyncio.run(automation.run_workflow("Broken", ctx))
    except ToolError as exc:
        assert "failed" in str(exc).lower()
    else:
        raise AssertionError("unknown tool should fail the workflow")


def test_create_workflow_validates_tools(ctx) -> None:
    registry = build_registry()
    ctx.extra["registry"] = registry
    result = asyncio.run(registry.execute("create_workflow", {"name": "X", "steps": '[{"tool":"nope","args":{}}]'}, ctx))
    assert result.ok is False
    assert "Unknown tool" in result.error


def test_emergency_stop_blocks_workflow(ctx) -> None:
    registry = build_registry()
    automation = AutomationController(registry, ctx.policy, ctx.ui, ctx.store)
    ctx.store.save_workflow("Blocked", "", [{"tool": "add_todo", "args": {"text": "never"}}])
    automation.emergency_stop()
    try:
        asyncio.run(automation.run_workflow("Blocked", ctx))
    except Exception as exc:
        assert "stop" in str(exc).lower() or "cancel" in str(exc).lower()
    else:
        raise AssertionError("emergency stop should prevent the workflow")