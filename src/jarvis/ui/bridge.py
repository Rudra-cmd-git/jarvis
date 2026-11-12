"""Qt implementation of the backend UI sink.

Signals are emitted from the asyncio worker thread; Qt queues them to the GUI
thread automatically. The backend never imports Qt.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from jarvis.core.events import UiSink  # noqa: F401 - documented protocol


class UiBridge(QObject):
    sig_token = Signal(str)
    sig_message = Signal(dict)
    sig_status = Signal(str)
    sig_state = Signal(str, str)
    sig_action = Signal(dict)
    sig_task = Signal(dict)
    sig_notify = Signal(str, str, str)
    sig_error = Signal(str)
    sig_settings_changed = Signal()
    sig_conversation_changed = Signal()
    sig_listening = Signal(float, bool)
    sig_history = Signal(list)
    sig_confirm = Signal(object, object)

    def token(self, text: str) -> None:
        self.sig_token.emit(text)

    def message(self, message: dict[str, Any]) -> None:
        self.sig_message.emit(message)

    def status(self, text: str) -> None:
        self.sig_status.emit(text)

    def state(self, state: str, detail: str = "") -> None:
        self.sig_state.emit(state, detail)

    def action(self, entry: dict[str, Any]) -> None:
        self.sig_action.emit(entry)

    def task(self, task: dict[str, Any]) -> None:
        self.sig_task.emit(task)

    def notify(self, title: str, body: str, level: str = "info") -> None:
        self.sig_notify.emit(title, body, level)

    def error(self, text: str) -> None:
        self.sig_error.emit(text)

    def settings_changed(self) -> None:
        self.sig_settings_changed.emit()

    def conversation_changed(self) -> None:
        self.sig_conversation_changed.emit()

    def listening(self, level: float, active: bool) -> None:
        self.sig_listening.emit(level, active)

    def history(self, messages: list[dict[str, Any]]) -> None:
        self.sig_history.emit(messages)

    def request_confirmation(self, request: Any, future: Any) -> None:
        self.sig_confirm.emit(request, future)