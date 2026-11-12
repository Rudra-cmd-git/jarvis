"""Tool registry: declaration, validation, execution, auditing.

A tool is a plain Python callable plus a JSON-schema description. The same
description is sent to the LLM, so what the model sees is exactly what runs.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import time
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from jarvis.core.errors import PermissionDenied, ToolError, ToolNotFound, ToolTimeout
from jarvis.core.util import truncate
from jarvis.security.permissions import ConfirmationRequest, Risk, format_arguments
from jarvis.tools.context import ToolContext

logger = logging.getLogger("jarvis.tools.registry")

# A dedicated executor avoids Python 3.15's lazy concurrent.futures attribute,
# which Qt's import hook can leave unresolved and which breaks asyncio.to_thread.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-tools")


async def _run_sync(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EXECUTOR, functools.partial(func, *args, **kwargs))


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str = ""
    risk: Risk = Risk.LOW
    duration_ms: int = 0
    verified: bool | None = None

    def as_text(self) -> str:
        if self.ok:
            if isinstance(self.output, str):
                return self.output
            try:
                return json.dumps(self.output, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                return str(self.output)
        return f"ERROR: {self.error}"


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    risk: Risk = Risk.LOW
    admin: bool = False
    timeout: float = 60.0
    hidden: bool = False
    category: str = "general"

    def schema(self) -> dict[str, Any]:
        params = self.parameters or {"type": "object", "properties": {}}
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ------------------------------------------------------------- registration
    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def register_all(self, specs: Iterable[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFound(f"Unknown tool '{name}'") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[name] for name in self.names()]

    def schemas(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        return [s.schema() for s in self.specs() if include_hidden or not s.hidden]

    def categories(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for spec in self.specs():
            result.setdefault(spec.category, []).append(spec.name)
        return result

    # ---------------------------------------------------------------- execution
    async def execute(
        self,
        name: str,
        args: dict[str, Any] | None,
        ctx: ToolContext,
        *,
        audit: bool = True,
    ) -> ToolResult:
        spec = self.get(name)
        args = args or {}
        started = time.monotonic()
        ctx.check_cancelled()

        try:
            _validate_arguments(spec, args)
            await _authorize(ctx, spec, args)
            if inspect.iscoroutinefunction(spec.handler):
                output = await asyncio.wait_for(spec.handler(ctx, **args), timeout=spec.timeout)
            else:
                output = await asyncio.wait_for(
                    _run_sync(spec.handler, ctx, **args), timeout=spec.timeout
                )
        except asyncio.TimeoutError as exc:
            result = ToolResult(
                ok=False,
                error=f"Timed out after {spec.timeout:.0f}s",
                risk=spec.risk,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except PermissionDenied as exc:
            result = ToolResult(
                ok=False,
                error=str(exc),
                risk=spec.risk,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except ToolError as exc:
            result = ToolResult(
                ok=False,
                error=str(exc),
                risk=spec.risk,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - tools must never crash the app
            logger.exception("Tool %s failed", name)
            result = ToolResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                risk=spec.risk,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        else:
            result = ToolResult(
                ok=True,
                output=output,
                risk=spec.risk,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        summary = _summarise(name, args, result)
        entry = {
            "tool": name,
            "risk": spec.risk.value,
            "ok": result.ok,
            "summary": summary,
            "duration_ms": result.duration_ms,
            "category": spec.category,
        }
        if audit:
            try:
                ctx.store.log_action(
                    tool=name,
                    risk=spec.risk.value,
                    ok=result.ok,
                    summary=summary,
                    detail=result.error if not result.ok else "",
                    duration_ms=result.duration_ms,
                )
            except Exception:  # pragma: no cover - logging must not break tools
                logger.exception("Could not write action log")
        ctx.ui.action(entry)
        return result


async def _authorize(ctx: ToolContext, spec: ToolSpec, args: dict[str, Any]) -> None:
    """Every tool call passes through the permission policy, regardless of caller."""
    policy = getattr(ctx, "policy", None)
    if policy is None:
        return
    decision = policy.evaluate(spec.name, spec.risk)
    if not decision.allowed:
        raise PermissionDenied(decision.reason)
    if not decision.needs_confirmation:
        return
    request = ConfirmationRequest(
        tool=spec.name,
        risk=spec.risk,
        summary=spec.description,
        detail="Review the arguments before approving.",
        arguments=args,
        human_args=format_arguments(args),
    )
    await policy.authorize(spec.name, spec.risk, request)


def _validate_arguments(spec: ToolSpec, args: dict[str, Any]) -> None:
    schema = spec.parameters or {}
    if schema.get("type") != "object":
        return
    required = schema.get("required", []) or []
    props = schema.get("properties", {}) or {}
    missing = [key for key in required if key not in args or args[key] is None]
    if missing:
        raise ToolError(f"Missing required argument(s) for {spec.name}: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = [key for key in args if key not in props]
        if unknown:
            raise ToolError(f"Unknown argument(s) for {spec.name}: {', '.join(unknown)}")
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in args.items():
        expected = props.get(key, {}).get("type")
        python_type = type_map.get(expected) if isinstance(expected, str) else None
        if python_type and not isinstance(value, python_type):
            if not (expected == "number" and isinstance(value, int)):
                raise ToolError(
                    f"Argument '{key}' of {spec.name} must be {expected}, got {type(value).__name__}"
                )


def _summarise(name: str, args: dict[str, Any], result: ToolResult) -> str:
    detail = format_arguments(args)
    head = detail.splitlines()[0] if detail else ""
    status = "ok" if result.ok else f"failed: {truncate(result.error, 160)}"
    return truncate(f"{name}({head}) -> {status}", 240)


__all__ = ["ToolSpec", "ToolResult", "ToolRegistry"]