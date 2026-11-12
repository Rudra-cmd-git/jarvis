"""Automation session control: cancellation, workflow execution, task reporting."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from jarvis.core.errors import Cancelled, ToolError
from jarvis.core.events import UiSink
from jarvis.security.permissions import PermissionPolicy
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.automation")


class AutomationController:
    """Owns the emergency-stop event and runs multi-step workflows."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: PermissionPolicy,
        ui: UiSink,
        store: Any,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.ui = ui
        self.store = store
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._active = 0
        self._on_stop: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ session
    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active > 0

    def new_session(self) -> threading.Event:
        self._cancel = threading.Event()
        with self._lock:
            self._active = 0
        return self._cancel

    def add_stop_hook(self, callback: Callable[[], None]) -> None:
        self._on_stop.append(callback)

    def emergency_stop(self) -> str:
        self._cancel.set()
        for callback in list(self._on_stop):
            try:
                callback()
            except Exception:
                logger.exception("Emergency stop hook failed")
        self.ui.state("stopped", "Emergency stop engaged")
        self.ui.notify("Automation stopped", "Emergency stop engaged. No further actions will run.", "warning")
        logger.warning("Emergency stop engaged")
        return "Emergency stop engaged."

    def reset(self) -> None:
        self._cancel = threading.Event()

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise Cancelled("Emergency stop")

    # ----------------------------------------------------------------- workflow
    async def run_workflow(self, name: str, ctx: ToolContext) -> str:
        workflow = self.store.get_workflow(name)
        if not workflow:
            raise ToolError(f"No workflow named '{name}'.")
        steps = workflow.get("steps") or []
        if not steps:
            raise ToolError(f"Workflow '{name}' has no steps.")
        self.check_cancelled()
        with self._lock:
            self._active += 1
        succeeded: list[str] = []
        failed: list[str] = []
        try:
            for index, step in enumerate(steps, start=1):
                self.check_cancelled()
                tool_name = step.get("tool", "")
                args = step.get("args") or {}
                try:
                    spec = self.registry.get(tool_name)
                except ToolError as exc:
                    failed.append(f"step {index}: {exc}")
                    continue

                self.ui.task(
                    {
                        "status": "running",
                        "title": name,
                        "step": index,
                        "total": len(steps),
                        "tool": tool_name,
                    }
                )

                result = await self.registry.execute(tool_name, args, ctx)
                if result.ok:
                    succeeded.append(tool_name)
                else:
                    failed.append(f"step {index} ({tool_name}): {result.error}")

            self.ui.task(
                {
                    "status": "done",
                    "title": name,
                    "step": len(steps),
                    "total": len(steps),
                    "succeeded": len(succeeded),
                    "failed": len(failed),
                }
            )
        finally:
            with self._lock:
                self._active = max(0, self._active - 1)

        if not succeeded:
            raise ToolError("Workflow failed: " + "; ".join(failed))
        summary = f"Workflow '{name}' finished: {len(succeeded)}/{len(steps)} steps succeeded."
        if failed:
            summary += " Failed: " + "; ".join(failed)
        return summary

    # ------------------------------------------------------------------ context
    def bind_context_factory(self, context_builder) -> None:
        """Remember how to build tool contexts (used by the app controller)."""
        self._context_builder = context_builder