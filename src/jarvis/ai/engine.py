"""The AI engine: streaming chat plus a verified tool-calling loop.

The loop is the "agent": it may call tools, inspect their real results, recover
from failures and continue until the user's request is satisfied or the
iteration budget is exhausted.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from jarvis.ai.client import ChatClient, parse_tool_arguments
from jarvis.ai.prompts import build_system_prompt, trim_history
from jarvis.ai.providers import resolve_endpoint
from jarvis.config import AppConfig
from jarvis.core.errors import Cancelled, PermissionDenied, ProviderError, ToolError
from jarvis.core.events import UiSink
from jarvis.core.util import truncate
from jarvis.security.permissions import PermissionPolicy
from jarvis.security.secrets import SecretStore
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolRegistry, ToolSpec

logger = logging.getLogger("jarvis.ai.engine")


@dataclass
class EngineResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    provider: str = ""
    model: str = ""
    cancelled: bool = False

    @property
    def used_tools(self) -> bool:
        return bool(self.tool_calls)


class AIEngine:
    def __init__(
        self,
        cfg: AppConfig,
        secrets: SecretStore,
        registry: ToolRegistry,
        policy: PermissionPolicy,
        ui: UiSink,
        context_factory: Callable[[str], ToolContext],
    ) -> None:
        self.cfg = cfg
        self.secrets = secrets
        self.registry = registry
        self.policy = policy
        self.ui = ui
        self._context_factory = context_factory

    def reload(self, cfg: AppConfig) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------- public
    async def chat(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        conversation_id: str = "",
        extra_context: str = "",
        memory: list[str] | None = None,
        stream: bool = True,
    ) -> EngineResult:
        endpoint = resolve_endpoint(self.cfg, self.secrets)
        client = ChatClient(endpoint, timeout=self.cfg.request_timeout)
        ctx = self._context_factory(conversation_id)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": build_system_prompt(
                    self.cfg,
                    memory=memory or [],
                    extra_context=extra_context,
                    tool_names=self.registry.names(),
                ),
            },
            *trim_history(history, self.cfg.history_limit),
            {"role": "user", "content": user_text},
        ]

        tools = self.registry.schemas()
        final_text = ""
        used_calls: list[dict[str, Any]] = []
        iterations = 0

        try:
            for iterations in range(1, self.cfg.max_tool_iterations + 1):
                ctx.check_cancelled()
                text_parts: list[str] = []
                call_map: dict[int, dict[str, Any]] = {}
                finish_reason = "stop"

                self.ui.state("thinking", f"Requesting {endpoint.model}")
                async for chunk in client.stream(
                    messages,
                    tools=tools or None,
                    temperature=self.cfg.temperature,
                    max_tokens=self.cfg.max_tokens,
                ):
                    if ctx.cancelled:
                        raise Cancelled("Emergency stop")
                    if chunk.kind == "text" and chunk.text:
                        text_parts.append(chunk.text)
                        if stream:
                            self.ui.token(chunk.text)
                    elif chunk.kind == "tool_call" and chunk.tool_call:
                        entry = call_map.setdefault(
                            chunk.tool_call.index, {"id": None, "name": "", "arguments": ""}
                        )
                        if chunk.tool_call.id:
                            entry["id"] = chunk.tool_call.id
                        if chunk.tool_call.name:
                            entry["name"] = chunk.tool_call.name
                        entry["arguments"] += chunk.tool_call.arguments
                    elif chunk.kind == "finish":
                        finish_reason = chunk.finish_reason or finish_reason

                assistant_text = "".join(text_parts).strip()
                final_text = assistant_text or final_text
                calls = [
                    {
                        "id": entry["id"] or f"call_{index}",
                        "type": "function",
                        "function": {"name": entry["name"], "arguments": entry["arguments"]},
                    }
                    for index, entry in sorted(call_map.items())
                    if entry["name"]
                ]

                if not calls:
                    if not assistant_text:
                        assistant_text = (
                            "I finished the request but have no textual result to report."
                            if finish_reason == "stop"
                            else "The provider stopped without a response."
                        )
                        final_text = assistant_text
                    self.ui.state("idle")
                    return EngineResult(
                        text=assistant_text,
                        tool_calls=used_calls,
                        iterations=iterations,
                        provider=endpoint.provider,
                        model=endpoint.model,
                    )

                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text or None,
                        "tool_calls": calls,
                    }
                )
                used_calls.extend(calls)

                for call in calls:
                    if ctx.cancelled:
                        raise Cancelled("Emergency stop")
                    name = call["function"]["name"]
                    raw_args = call["function"]["arguments"]
                    try:
                        arguments = parse_tool_arguments(raw_args)
                    except ValueError as exc:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": f"Invalid arguments: {exc}",
                            }
                        )
                        continue

                    result_text = await self._run_tool(ctx, call["id"], name, arguments, messages)
                    if ctx.cancelled:
                        raise Cancelled("Emergency stop")
                    final_text = f"{final_text}\n{result_text}".strip() if final_text else result_text

            self.ui.state("idle")
            return EngineResult(
                text=(
                    final_text
                    or f"I reached the {self.cfg.max_tool_iterations}-step limit for this request. "
                    "Please narrow the task or raise the limit in Settings."
                ),
                tool_calls=used_calls,
                iterations=iterations,
                provider=endpoint.provider,
                model=endpoint.model,
            )
        except Cancelled:
            self.ui.state("idle")
            return EngineResult(
                text=truncate(final_text, 2000) or "Stopped.",
                tool_calls=used_calls,
                iterations=iterations,
                provider=endpoint.provider,
                model=endpoint.model,
                cancelled=True,
            )
        except PermissionDenied as exc:
            self.ui.state("idle")
            return EngineResult(
                text=f"Permission denied: {exc}",
                tool_calls=used_calls,
                iterations=iterations,
                provider=endpoint.provider,
                model=endpoint.model,
            )
        except ProviderError as exc:
            self.ui.state("idle")
            logger.exception("Provider failure")
            return EngineResult(
                text=f"AI provider error: {exc}",
                tool_calls=used_calls,
                iterations=iterations,
                provider=endpoint.provider,
                model=endpoint.model,
            )
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors safely
            self.ui.state("idle")
            logger.exception("Engine failure")
            return EngineResult(
                text=f"Unexpected error: {type(exc).__name__}: {exc}",
                tool_calls=used_calls,
                iterations=iterations,
                provider=endpoint.provider,
                model=endpoint.model,
            )
        finally:
            await client.close()

    async def test_connection(self) -> tuple[bool, str]:
        endpoint = resolve_endpoint(self.cfg, self.secrets)
        client = ChatClient(endpoint, timeout=min(30.0, self.cfg.request_timeout))
        try:
            result = await client.complete(
                [{"role": "user", "content": "Reply with the single word: ready"}],
                max_tokens=16,
                temperature=0,
            )
            return True, f"Connected to {endpoint.provider} using {endpoint.model}. Reply: {result.text.strip()!r}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            await client.close()

    # ------------------------------------------------------------------ private
    async def _run_tool(
        self,
        ctx: ToolContext,
        call_id: str,
        name: str,
        arguments: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> str:
        try:
            spec: ToolSpec = self.registry.get(name)
        except ToolError as exc:
            message = str(exc)
            messages.append({"role": "tool", "tool_call_id": call_id, "content": message})
            return message

        self.ui.status(f"Running {name}")
        self.ui.state("working", f"{name}")
        try:
            result = await self.registry.execute(name, arguments, ctx)
        except ToolError as exc:
            message = f"{name} failed: {exc}"
            messages.append({"role": "tool", "tool_call_id": call_id, "content": message})
            return message
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled tool error")
            message = f"{name} crashed: {type(exc).__name__}: {exc}"
            messages.append({"role": "tool", "tool_call_id": call_id, "content": message})
            return message

        text = result.as_text()
        messages.append({"role": "tool", "tool_call_id": call_id, "content": text})
        if result.ok:
            self.ui.status(f"{name} completed in {result.duration_ms} ms")
        else:
            self.ui.status(f"{name} failed: {truncate(result.error, 120)}")
        return text