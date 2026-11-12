"""Streaming chat client built on the OpenAI SDK.

Only the Chat Completions surface is used, which every supported provider
implements. The client yields normalised chunk dictionaries so the engine does
not depend on SDK internals.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from jarvis.ai.providers import ResolvedEndpoint
from jarvis.core.errors import (
    JarvisError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger("jarvis.ai.client")


@dataclass
class ToolCallDelta:
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


@dataclass
class StreamChunk:
    kind: str  # "text" | "tool_call" | "finish" | "error"
    text: str = ""
    tool_call: ToolCallDelta | None = None
    finish_reason: str | None = None
    error: str = ""


@dataclass
class CompletionResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"


class ChatClient:
    def __init__(self, endpoint: ResolvedEndpoint, timeout: float = 90.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.endpoint.api_key,
                base_url=self.endpoint.base_url,
                timeout=self.timeout,
                max_retries=1,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # pragma: no cover
                pass
            self._client = None

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.6,
        max_tokens: int = 1200,
    ) -> AsyncIterator[StreamChunk]:
        kwargs: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = await self._get_client().chat.completions.create(**kwargs)
            async for event in stream:
                chunk = _translate(event)
                if chunk is not None:
                    yield chunk
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise _map_error(exc) from exc

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.6,
        max_tokens: int = 1200,
    ) -> CompletionResult:
        chunks: list[StreamChunk] = []
        async for chunk in self.stream(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens
        ):
            chunks.append(chunk)
        return _collapse(chunks)


def _translate(event: Any) -> StreamChunk | None:
    """Convert one SDK chunk into a StreamChunk (best-effort, version tolerant)."""
    choices = getattr(event, "choices", None)
    if not choices:
        return None
    choice = choices[0]
    delta = getattr(choice, "delta", None)
    finish = getattr(choice, "finish_reason", None)
    if finish:
        return StreamChunk(kind="finish", finish_reason=finish)
    if delta is None:
        return None
    text = getattr(delta, "content", None)
    if text:
        return StreamChunk(kind="text", text=text)
    tool_calls = getattr(delta, "tool_calls", None) or []
    for call in tool_calls:
        function = getattr(call, "function", None)
        index = getattr(call, "index", 0) or 0
        name = getattr(function, "name", None) if function else None
        args = getattr(function, "arguments", None) if function else None
        if name or args:
            return StreamChunk(
                kind="tool_call",
                tool_call=ToolCallDelta(
                    index=index,
                    id=getattr(call, "id", None),
                    name=name,
                    arguments=args or "",
                ),
            )
    return None


def _collapse(chunks: list[StreamChunk]) -> CompletionResult:
    text_parts: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    finish = "stop"
    for chunk in chunks:
        if chunk.kind == "text":
            text_parts.append(chunk.text)
        elif chunk.kind == "tool_call" and chunk.tool_call:
            entry = calls.setdefault(
                chunk.tool_call.index, {"id": None, "name": "", "arguments": ""}
            )
            if chunk.tool_call.id:
                entry["id"] = chunk.tool_call.id
            if chunk.tool_call.name:
                entry["name"] = chunk.tool_call.name
            entry["arguments"] += chunk.tool_call.arguments
        elif chunk.kind == "finish" and chunk.finish_reason:
            finish = chunk.finish_reason
    tool_calls = [
        {
            "id": entry["id"] or f"call_{index}",
            "type": "function",
            "function": {"name": entry["name"], "arguments": entry["arguments"]},
        }
        for index, entry in sorted(calls.items())
        if entry["name"]
    ]
    return CompletionResult(text="".join(text_parts), tool_calls=tool_calls, finish_reason=finish)


def _map_error(exc: Exception) -> ProviderError:
    if isinstance(exc, JarvisError):
        return exc
    name = type(exc).__name__.lower()
    message = str(exc)
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if "auth" in name or status == 401 or "api key" in message.lower():
        return ProviderAuthError(f"Provider rejected the API key: {message}")
    if "ratelimit" in name or status == 429:
        return ProviderRateLimitError(f"Provider rate limit reached: {message}")
    if "timeout" in name or "timed out" in message.lower():
        return ProviderError(f"Provider timed out: {message}")
    return ProviderError(f"Provider error: {message}")


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Some models emit single quotes or trailing commas; try a light repair.
        try:
            parsed = json.loads(raw.replace("'", '"').replace(",}", "}").replace(",]", "]"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model produced invalid JSON arguments: {raw[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return parsed