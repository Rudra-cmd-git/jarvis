"""Integration tests for the AI client against a local mock OpenAI server.

These tests verify our request/response handling without calling a real provider.
They do NOT prove that DeepSeek/OpenRouter work; they prove our client speaks the
protocol correctly and handles streaming, tool calls and API errors.
"""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jarvis.ai.engine import AIEngine
from jarvis.tools.builtin import build_registry


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        model = body.get("model", "mock")

        if model == "mock-error":
            payload = json.dumps({"error": {"message": "invalid api key"}}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        messages = body.get("messages", [])
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        wants_tool = "tool" in last_user.lower() and not has_tool_result

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def chunk(delta: dict, finish: str | None = None) -> None:
            payload = {
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())

        if wants_tool:
            chunk(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_mock",
                            "type": "function",
                            "function": {
                                "name": "add_todo",
                                "arguments": json.dumps({"text": "mock task"}),
                            },
                        }
                    ],
                }
            )
            chunk({}, "tool_calls")
        elif has_tool_result:
            chunk({"role": "assistant", "content": "Done."})
            chunk({}, "stop")
        else:
            chunk({"role": "assistant", "content": "Hello from mock."})
            chunk({}, "stop")
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args) -> None:  # silence test server
        pass


@pytest.fixture(scope="module")
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def _engine(cfg, ctx, base_url: str, model: str = "mock") -> AIEngine:
    cfg.provider = "custom"
    cfg.base_url = base_url
    cfg.model = model
    cfg.request_timeout = 10.0
    return AIEngine(
        cfg,
        ctx.secrets,
        build_registry(),
        ctx.policy,
        ctx.ui,
        lambda _conversation_id: ctx,
    )


def test_mock_streaming_text(cfg, ctx, mock_server, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_API_KEY", "test-key")
    engine = _engine(cfg, ctx, mock_server)
    result = asyncio.run(engine.chat("hello there", []))
    assert result.text == "Hello from mock."
    assert result.tool_calls == []
    assert "Hello from mock." in "".join(ctx.ui.texts("token"))


def test_mock_tool_call_executes(cfg, ctx, mock_server, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_API_KEY", "test-key")
    engine = _engine(cfg, ctx, mock_server)
    result = asyncio.run(engine.chat("please use a tool", []))
    assert result.text == "Done."
    assert result.used_tools
    assert ctx.store.list_todos()[0]["text"] == "mock task"


def test_mock_auth_error_is_reported(cfg, ctx, mock_server, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_API_KEY", "test-key")
    engine = _engine(cfg, ctx, mock_server, model="mock-error")
    result = asyncio.run(engine.chat("hello", []))
    assert "provider error" in result.text.lower()
    assert "invalid api key" in result.text.lower()