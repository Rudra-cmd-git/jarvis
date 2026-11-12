"""Risk classification and confirmation policy.

Every tool declares a risk level. The policy decides whether an action may run
without asking, must ask the user, or is refused outright. The UI supplies a
confirmer callable; in headless/test contexts the default is "deny".
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from jarvis.config import AppConfig
from jarvis.core.util import is_within

logger = logging.getLogger("jarvis.security.permissions")


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def label(self) -> str:
        return {"low": "Low risk", "medium": "Medium risk", "high": "High risk"}[self.value]


class ConfirmationResult(Enum):
    ALLOW = "allow"
    ALLOW_ALWAYS = "always"
    DENY = "deny"


@dataclass
class ConfirmationRequest:
    tool: str
    risk: Risk
    summary: str
    detail: str = ""
    arguments: dict = field(default_factory=dict)
    human_args: str = ""

    def describe(self) -> str:
        lines = [f"{self.tool}  [{self.risk.label}]", self.summary]
        if self.human_args:
            lines.append("")
            lines.append(self.human_args)
        if self.detail:
            lines.append("")
            lines.append(self.detail)
        return "\n".join(lines)


class Confirmer(Protocol):
    def __call__(self, request: ConfirmationRequest) -> Awaitable[ConfirmationResult]: ...


async def deny_confirmer(request: ConfirmationRequest) -> ConfirmationResult:
    logger.warning("No confirmer attached; denying %s", request.tool)
    return ConfirmationResult.DENY


@dataclass
class PermissionDecision:
    risk: Risk
    needs_confirmation: bool
    reason: str
    allowed: bool = True


class PermissionPolicy:
    """Stateless-ish gatekeeper shared by the engine and the UI."""

    def __init__(self, cfg: AppConfig, confirmer: Confirmer | None = None) -> None:
        self.cfg = cfg
        self._confirmer: Confirmer = confirmer or deny_confirmer
        self._always_allow: set[str] = set()

    # ------------------------------------------------------------------ wiring
    def set_confirmer(self, confirmer: Confirmer) -> None:
        self._confirmer = confirmer

    def reload(self, cfg: AppConfig) -> None:
        self.cfg = cfg

    def reset_session_grants(self) -> None:
        self._always_allow.clear()

    # --------------------------------------------------------------- decisions
    def evaluate(self, tool: str, risk: Risk) -> PermissionDecision:
        if tool in self._always_allow:
            return PermissionDecision(risk, False, "Allowed for this session")
        if risk is Risk.LOW:
            return PermissionDecision(risk, False, "Low-risk action")
        if risk is Risk.HIGH:
            if not self.cfg.allow_high_risk:
                return PermissionDecision(
                    risk,
                    False,
                    "High-risk actions are disabled. Enable them in Settings > Security if you understand the consequences.",
                    allowed=False,
                )
            return PermissionDecision(risk, True, "High-risk action requires explicit confirmation")
        if self.cfg.confirm_medium:
            return PermissionDecision(risk, True, "Medium-risk action requires confirmation")
        return PermissionDecision(risk, False, "Medium-risk confirmations are disabled in settings")

    async def authorize(self, tool: str, risk: Risk, request: ConfirmationRequest) -> None:
        """Raise PermissionDenied when the action must not proceed."""
        from jarvis.core.errors import PermissionDenied

        decision = self.evaluate(tool, risk)
        if not decision.allowed:
            raise PermissionDenied(decision.reason)
        if not decision.needs_confirmation:
            return
        result = await self._confirmer(request)
        if result is ConfirmationResult.DENY:
            raise PermissionDenied(f"User declined: {request.summary}")
        if result is ConfirmationResult.ALLOW_ALWAYS:
            self._always_allow.add(tool)

    # ------------------------------------------------------------------- paths
    def path_allowed(self, path: str | Path) -> bool:
        return any(is_within(path, root) for root in self.cfg.allowed_roots)

    def require_path(self, path: str | Path) -> Path:
        from jarvis.core.errors import PermissionDenied

        resolved = Path(path).expanduser()
        if not self.path_allowed(resolved):
            allowed = ", ".join(self.cfg.allowed_roots)
            raise PermissionDenied(
                f"'{resolved}' is outside the folders JARVIS may use.\nAllowed folders: {allowed}\n"
                "Add the folder in Settings > Security."
            )
        return resolved

    def summary_for(self, tool: str, risk: Risk, detail: str) -> str:
        return f"{tool}: {detail} [{risk.label}]"


def format_arguments(arguments: dict) -> str:
    if not arguments:
        return ""
    parts = []
    for key, value in arguments.items():
        text = str(value)
        if len(text) > 300:
            text = text[:300] + "…"
        parts.append(f"{key}: {text}")
    return "\n".join(parts)


def run_blocking(coro: Awaitable) -> object:
    """Helper for tests: run a coroutine to completion."""
    return asyncio.run(coro) if asyncio.iscoroutine(coro) else coro


__all__ = [
    "Risk",
    "ConfirmationResult",
    "ConfirmationRequest",
    "PermissionDecision",
    "PermissionPolicy",
    "format_arguments",
    "run_blocking",
]