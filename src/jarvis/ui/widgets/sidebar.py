"""Left navigation rail."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from jarvis.ui import theme

_ITEMS = [
    ("chat", "Chat"),
    ("tasks", "Tasks"),
    ("memory", "Memory"),
    ("history", "History"),
    ("workflows", "Workflows"),
    ("settings", "Settings"),
]


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedWidth(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(6)

        mark = QLabel("J")
        mark.setObjectName("Brand")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFont(QFont(theme.FONT, 20, QFont.Bold))
        mark.setStyleSheet(f"color: {theme.CYAN}; border: 1px solid {theme.CYAN_DARK}; border-radius: 12px; padding: 6px;")
        layout.addWidget(mark)
        layout.addSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, label in _ITEMS:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFont(QFont(theme.FONT, 9))
            button.clicked.connect(lambda _checked=False, name=key: self.navigate.emit(name))
            self._group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.status_dot = QLabel("●")
        self.status_dot.setAlignment(Qt.AlignCenter)
        self.status_dot.setStyleSheet(f"color: {theme.OK}; font-size: 12px;")
        self.status_dot.setToolTip("JARVIS running")
        layout.addWidget(self.status_dot)
        self.set_active("chat")

    def set_active(self, name: str) -> None:
        button = self.buttons.get(name)
        if button is not None:
            button.setChecked(True)

    def set_running(self, running: bool) -> None:
        colour = theme.OK if running else theme.DANGER
        self.status_dot.setStyleSheet(f"color: {colour}; font-size: 12px;")
        self.status_dot.setToolTip("JARVIS running" if running else "JARVIS stopped")