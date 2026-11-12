"""Command input with push-to-talk."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import theme


class MicButton(QPushButton):
    pressed_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Hold to talk", parent)
        self.setObjectName("Primary")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(False)
        self._holding = False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._holding = True
            self.setDown(True)
            self.pressed_changed.emit(True)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._holding:
            self._holding = False
            self.setDown(False)
            self.pressed_changed.emit(False)
        super().mouseReleaseEvent(event)

    def set_active(self, active: bool) -> None:
        self.setText("Listening…" if active else "Hold to talk")
        self.setStyleSheet(
            f"background-color: {theme.CYAN_DARK}; color: {theme.CYAN};"
            if active
            else ""
        )


class CommandEdit(QTextEdit):
    send_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setPlaceholderText("Ask JARVIS, or describe a task for your PC…")
        self.setFixedHeight(58)
        self.setFont(QFont(theme.FONT, 10))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            self.send_requested.emit()
            return
        super().keyPressEvent(event)

    def text(self) -> str:
        return self.toPlainText().strip()


class InputBar(QFrame):
    send_requested = Signal(str)
    push_to_talk = Signal(bool)
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = CommandEdit(self)
        self.edit.send_requested.connect(self._emit_send)
        row.addWidget(self.edit, 1)

        self.mic = MicButton(self)
        self.mic.pressed_changed.connect(self.push_to_talk.emit)
        self.mic.setEnabled(True)
        row.addWidget(self.mic)

        self.send_button = QPushButton("Send", self)
        self.send_button.setObjectName("Primary")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.clicked.connect(self._emit_send)
        row.addWidget(self.send_button)

        self.stop_button = QPushButton("Stop", self)
        self.stop_button.setObjectName("Danger")
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.setVisible(False)
        row.addWidget(self.stop_button)
        layout.addLayout(row)

        hint = QLabel("Enter to send · Shift+Enter for a new line · Push and hold the mic to speak")
        hint.setObjectName("Muted")
        hint.setFont(QFont(theme.FONT, 8))
        layout.addWidget(hint)

    def _emit_send(self) -> None:
        text = self.edit.text()
        if text:
            self.send_requested.emit(text)
            self.edit.clear()

    def set_busy(self, busy: bool) -> None:
        self.stop_button.setVisible(busy)
        self.send_button.setEnabled(not busy)

    def set_listening(self, listening: bool) -> None:
        self.mic.set_active(listening)

    def set_voice_enabled(self, enabled: bool) -> None:
        self.mic.setEnabled(enabled)
        self.mic.setToolTip(
            "Push and hold to speak" if enabled else "Voice input is disabled in Settings > Voice"
        )