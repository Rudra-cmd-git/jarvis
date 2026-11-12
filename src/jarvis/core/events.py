"""UI event contracts.

The backend never imports Qt. It talks to a :class:`UiSink`; the UI layer
implements it with Qt signals, and tests use a recording sink.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UiSink(Protocol):
    def token(self, text: str) -> None: ...

    def message(self, message: dict[str, Any]) -> None: ...

    def status(self, text: str) -> None: ...

    def state(self, state: str, detail: str = "") -> None: ...

    def action(self, entry: dict[str, Any]) -> None: ...

    def task(self, task: dict[str, Any]) -> None: ...

    def notify(self, title: str, body: str, level: str = "info") -> None: ...

    def error(self, text: str) -> None: ...

    def settings_changed(self) -> None: ...

    def conversation_changed(self) -> None: ...

    def listening(self, level: float, active: bool) -> None: ...

    def history(self, messages: list[dict[str, Any]]) -> None: ...


class NullSink:
    """Discards every event. Useful for CLI/tests."""

    def token(self, text: str) -> None:
        pass

    def message(self, message: dict[str, Any]) -> None:
        pass

    def status(self, text: str) -> None:
        pass

    def state(self, state: str, detail: str = "") -> None:
        pass

    def action(self, entry: dict[str, Any]) -> None:
        pass

    def task(self, task: dict[str, Any]) -> None:
        pass

    def notify(self, title: str, body: str, level: str = "info") -> None:
        pass

    def error(self, text: str) -> None:
        pass

    def settings_changed(self) -> None:
        pass

    def conversation_changed(self) -> None:
        pass

    def listening(self, level: float, active: bool) -> None:
        pass

    def history(self, messages: list[dict[str, Any]]) -> None:
        pass


class RecordingSink(NullSink):
    """Test double that keeps every event in memory."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def _record(self, name: str, payload: Any = None) -> None:
        self.events.append((name, payload))

    def token(self, text: str) -> None:
        self._record("token", text)

    def message(self, message: dict[str, Any]) -> None:
        self._record("message", message)

    def status(self, text: str) -> None:
        self._record("status", text)

    def state(self, state: str, detail: str = "") -> None:
        self._record("state", (state, detail))

    def action(self, entry: dict[str, Any]) -> None:
        self._record("action", entry)

    def task(self, task: dict[str, Any]) -> None:
        self._record("task", task)

    def notify(self, title: str, body: str, level: str = "info") -> None:
        self._record("notify", (title, body, level))

    def error(self, text: str) -> None:
        self._record("error", text)

    def settings_changed(self) -> None:
        self._record("settings_changed")

    def conversation_changed(self) -> None:
        self._record("conversation_changed")

    def listening(self, level: float, active: bool) -> None:
        self._record("listening", (level, active))

    def history(self, messages: list[dict[str, Any]]) -> None:
        self._record("history", messages)

    def texts(self, name: str) -> list[str]:
        return [payload for event, payload in self.events if event == name]