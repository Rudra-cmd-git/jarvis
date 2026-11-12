import asyncio

import pytest

from jarvis.ai import engine as engine_module
from jarvis.ai.client import StreamChunk, ToolCallDelta
from jarvis.ai.engine import AIEngine
from jarvis.security.permissions import PermissionPolicy
from jarvis.tools.builtin import build_registry


class FakeClient:
    def __init__(self, scripts) -> None:
        self.scripts = list(scripts)
        self.closed = False

    async def stream(self, _messages, **_kwargs):
        script = self.scripts.pop(0) if self.scripts else []
        for chunk in script:
            yield chunk

    async def complete(self, _messages, **_kwargs):  # pragma: no cover - unused here
        chunks = []
        async for chunk in self.stream(_messages):
            chunks.append(chunk)
        return "".join(chunk.text for chunk in chunks if chunk.kind == "text")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def _text_engine(cfg, ctx, scripts, monkeypatch):
    registry = build_registry()
    fake = FakeClient(scripts)
    monkeypatch.setattr(engine_module, "ChatClient", lambda *a, **k: fake)
    engine = AIEngine(cfg, ctx.secrets, registry, ctx.policy, ctx.ui, lambda _cid: ctx)
    return engine, fake


def test_plain_text_response(cfg, ctx, monkeypatch) -> None:
    engine, fake = _text_engine(
        cfg,
        ctx,
        [[StreamChunk(kind="text", text="Hello there"), StreamChunk(kind="finish", finish_reason="stop")]],
        monkeypatch,
    )
    result = asyncio.run(engine.chat("hi", []))
    assert result.text == "Hello there"
    assert result.tool_calls == []
    assert fake.closed
    assert "Hello there" in "".join(ctx.ui.texts("token"))


def test_tool_calling_loop(cfg, ctx, monkeypatch) -> None:
    engine, fake = _text_engine(
        cfg,
        ctx,
        [
            [
                StreamChunk(
                    kind="tool_call",
                    tool_call=ToolCallDelta(index=0, id="call_1", name="add_todo", arguments='{"text":"walk"}'),
                ),
                StreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            [StreamChunk(kind="text", text="Added it."), StreamChunk(kind="finish", finish_reason="stop")],
        ],
        monkeypatch,
    )
    result = asyncio.run(engine.chat("remind me to walk", []))
    assert result.text == "Added it."
    assert result.used_tools
    assert ctx.store.list_todos()[0]["text"] == "walk"


def test_invalid_tool_arguments_are_reported_back(cfg, ctx, monkeypatch) -> None:
    engine, _ = _text_engine(
        cfg,
        ctx,
        [
            [
                StreamChunk(
                    kind="tool_call",
                    tool_call=ToolCallDelta(index=0, id="c1", name="add_todo", arguments="{not json"),
                ),
                StreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            [StreamChunk(kind="text", text="I could not add that."), StreamChunk(kind="finish", finish_reason="stop")],
        ],
        monkeypatch,
    )
    result = asyncio.run(engine.chat("add a task", []))
    assert result.text == "I could not add that."
    assert ctx.store.list_todos() == []


def test_provider_error_is_returned_as_text(cfg, ctx, monkeypatch) -> None:
    class BrokenClient(FakeClient):
        async def stream(self, _messages, **_kwargs):
            raise RuntimeError("upstream exploded")
            yield  # pragma: no cover

    fake = BrokenClient([])
    monkeypatch.setattr(engine_module, "ChatClient", lambda *a, **k: fake)
    engine = AIEngine(cfg, ctx.secrets, build_registry(), ctx.policy, ctx.ui, lambda _cid: ctx)
    result = asyncio.run(engine.chat("hi", []))
    assert "error" in result.text.lower()
    assert "upstream exploded" in result.text