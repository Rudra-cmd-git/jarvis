"""Runtime context handed to every tool."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from jarvis.config import AppConfig, AppPaths
    from jarvis.core.events import UiSink
    from jarvis.security.permissions import PermissionPolicy
    from jarvis.security.secrets import SecretStore


@dataclass
class ToolContext:
    """Everything a tool is allowed to know.

    Tools must never reach for global state; they receive this object so they
    can be unit-tested in isolation.
    """

    config: "AppConfig"
    paths: "AppPaths"
    store: Any
    secrets: "SecretStore"
    policy: "PermissionPolicy"
    ui: "UiSink"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    session_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        from jarvis.core.errors import Cancelled

        if self.cancel_event.is_set():
            raise Cancelled("Operation cancelled by user")

    def screenshot_dir(self) -> Path:
        self.paths.screenshot_dir.mkdir(parents=True, exist_ok=True)
        return self.paths.screenshot_dir