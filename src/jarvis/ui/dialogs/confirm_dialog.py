"""Confirmation dialog for medium- and high-risk actions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.security.permissions import ConfirmationRequest, ConfirmationResult, Risk
from jarvis.ui import theme

_RISK_COLOUR = {Risk.LOW: theme.CYAN, Risk.MEDIUM: theme.WARN, Risk.HIGH: theme.DANGER}


class ConfirmDialog(QDialog):
    def __init__(self, request: ConfirmationRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.request = request
        self.result = ConfirmationResult.DENY
        self.setWindowTitle("Confirm action")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(theme.stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        badge = QLabel(request.risk.label.upper())
        badge.setFont(QFont(theme.FONT, 9, QFont.Bold))
        colour = _RISK_COLOUR[request.risk]
        badge.setStyleSheet(
            f"color: {colour}; border: 1px solid {colour}; border-radius: 6px; padding: 3px 8px;"
        )
        header.addWidget(badge)
        header.addStretch(1)
        layout.addLayout(header)

        title = QLabel(request.tool)
        title.setFont(QFont(theme.FONT, 15, QFont.Bold))
        title.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(title)

        summary = QLabel(request.summary)
        summary.setWordWrap(True)
        summary.setFont(QFont(theme.FONT, 10))
        summary.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(summary)

        if request.human_args:
            args = QFrame()
            args.setObjectName("CardAlt")
            args_layout = QVBoxLayout(args)
            args_layout.setContentsMargins(12, 10, 12, 10)
            args_title = QLabel("ARGUMENTS")
            args_title.setObjectName("Muted")
            args_title.setFont(QFont(theme.FONT, 8))
            args_layout.addWidget(args_title)
            body = QLabel(request.human_args)
            body.setFont(QFont("Consolas", 9))
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            args_layout.addWidget(body)
            layout.addWidget(args)

        if request.detail:
            detail = QLabel(request.detail)
            detail.setWordWrap(True)
            detail.setFont(QFont(theme.FONT, 9))
            detail.setStyleSheet(f"color: {theme.MUTED};")
            layout.addWidget(detail)

        self.ack = QCheckBox(
            "I understand this changes something outside JARVIS and may not be reversible."
        )
        self.ack.setVisible(request.risk is Risk.HIGH)
        layout.addWidget(self.ack)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        deny = QPushButton("Deny", self)
        deny.setObjectName("Ghost")
        deny.clicked.connect(lambda: self._finish(ConfirmationResult.DENY))
        buttons.addWidget(deny)

        allow = QPushButton("Allow once", self)
        allow.setObjectName("Primary")
        allow.setCursor(Qt.PointingHandCursor)
        allow.clicked.connect(self._allow_once)
        buttons.addWidget(allow)

        if request.risk is Risk.MEDIUM:
            always = QPushButton("Allow always", self)
            always.setObjectName("Ghost")
            always.clicked.connect(lambda: self._finish(ConfirmationResult.ALLOW_ALWAYS))
            buttons.addWidget(always)

        layout.addLayout(buttons)
        self.allow_button = allow

    def _allow_once(self) -> None:
        if self.request.risk is Risk.HIGH and not self.ack.isChecked():
            self.ack.setToolTip("Tick the confirmation box to proceed.")
            return
        self._finish(ConfirmationResult.ALLOW)

    def _finish(self, result: ConfirmationResult) -> None:
        self.result = result
        self.accept()