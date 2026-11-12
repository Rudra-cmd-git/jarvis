import asyncio

import pytest

from jarvis.core.errors import ToolNotFound
from jarvis.tools.builtin import build_registry
from jarvis.tools.registry import ToolRegistry, ToolResult, ToolSpec


def _registry() -> ToolRegistry:
    return build_registry()


def test_all_specs_have_valid_schemas() -> None:
    registry = _registry()
    assert len(registry.names()) >= 50
    for spec in registry.specs():
        schema = spec.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == spec.name
        assert "description" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"


def test_unknown_tool_raises() -> None:
    registry = _registry()
    with pytest.raises(ToolNotFound):
        registry.get("definitely_not_a_tool")


def test_missing_argument_is_reported() -> None:
    registry = _registry()
    result = asyncio.run(registry.execute("open_app", {}, _dummy_context()))
    assert result.ok is False
    assert "Missing required argument" in result.error


def test_low_risk_tool_executes_and_logs(ctx) -> None:
    registry = _registry()
    result = asyncio.run(registry.execute("add_todo", {"text": "Buy milk"}, ctx))
    assert result.ok is True
    assert ctx.store.list_todos()[0]["text"] == "Buy milk"
    assert any(event == "action" for event, _ in ctx.ui.events)


def test_tool_exception_becomes_result(ctx) -> None:
    registry = ToolRegistry()

    def explode(_ctx):
        raise RuntimeError("boom")

    registry.register(ToolSpec(name="boom", description="fails", handler=explode))
    result = asyncio.run(registry.execute("boom", {}, ctx))
    assert result.ok is False
    assert "boom" in result.error


def _dummy_context():
    from jarvis.core.events import RecordingSink
    from jarvis.security.secrets import SecretStore
    from jarvis.security.permissions import PermissionPolicy
    from jarvis.tools.context import ToolContext
    from jarvis.config import AppConfig, AppPaths
    from jarvis.memory.store import Store
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    paths = AppPaths(tmp / "c", tmp / "d", tmp / "l", tmp / "m", tmp / "s", tmp / "p")
    paths.ensure()
    config = AppConfig()
    config.allowed_roots = [str(tmp)]
    store = Store(paths.database_file)
    return ToolContext(
        config=config,
        paths=paths,
        store=store,
        secrets=SecretStore(paths.secrets_file),
        policy=PermissionPolicy(config),
        ui=RecordingSink(),
    )