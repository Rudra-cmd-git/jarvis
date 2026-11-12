"""Toast host without window-opacity tricks (child widgets are not windows)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import theme

_LEVEL_COLOURS = {
    "success": theme.OK,
    "warning": theme.WARN,
    "error": theme.DANGER,
    "info": theme.CYAN,
}


class Toast(QFrame):
    def __init__(self, title: str, body: str, level: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        accent = _LEVEL_COLOURS.get(level, theme.CYAN)
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.PANEL_ALT}; border: 1px solid {theme.BORDER};"
            f" border-left: 3px solid {accent}; border-radius: 8px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(Qt.black)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        heading = QLabel(title)
        heading.setFont(QFont(theme.FONT, 10, QFont.Bold))
        heading.setStyleSheet(f"color: {accent}; background: transparent;")
        layout.addWidget(heading)
        message = QLabel(body)
        message.setWordWrap(True)
        message.setFont(QFont(theme.FONT, 9))
        message.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")
        message.setMaximumWidth(320)
        layout.addWidget(message)
        self.setMaximumWidth(360)


class ToastHost(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 16, 16)
        self.layout.setSpacing(8)
        self.layout.addStretch(1)

    def show(self, title: str, body: str, level: str = "info", timeout_ms: int = 5200) -> None:
        toast = Toast(title, body, level, self)
        self.layout.addWidget(toast, 0, Qt.AlignRight | Qt.AlignBottom)
        while self.layout.count() > 5:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        QTimer.singleShot(timeout_ms, lambda: self._dismiss(toast))

    def _dismiss(self, toast: Toast | None) -> None:
        if toast is None:
            return
        try:
            self.layout.removeWidget(toast)
            toast.deleteLater()
        except RuntimeError:
            pass