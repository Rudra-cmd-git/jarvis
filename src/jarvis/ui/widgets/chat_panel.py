"""Conversation panel with lightweight Markdown rendering."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import theme
from jarvis.core.util import now_iso

_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)
_LINK_RE = re.compile(r"(https?://[^\s<>()]+)")


def _inline_html(chunk: str) -> str:
    chunk = html.escape(chunk)
    chunk = _INLINE_CODE_RE.sub(
        lambda m: f'<span style="font-family:{theme.MONO};background:#07121c;padding:1px 4px;border-radius:3px;">{m.group(1)}</span>',
        chunk,
    )
    chunk = _BOLD_RE.sub(r"<b>\1</b>", chunk)
    chunk = _ITALIC_RE.sub(r"<i>\1</i>", chunk)
    chunk = _LINK_RE.sub(r'<a href="\1" style="color:#3fe0ff;">\1</a>', chunk)
    chunk = chunk.replace("\r\n", "\n")
    return chunk.replace("\n", "<br>")


def render_markdown(text: str) -> str:
    """Convert a small, safe subset of Markdown to Qt rich text.

    Code fences are split out before inline formatting so their HTML is escaped
    exactly once and never mangled by the inline pass.
    """
    if not text:
        return ""
    parts = _FENCE_RE.split(text)
    rendered: list[str] = []
    for index in range(0, len(parts), 3):
        rendered.append(_inline_html(parts[index]))
        if index + 2 < len(parts):
            code = html.escape(parts[index + 2].strip("\n"))
            rendered.append(
                f'<pre style="background:#050a12;border:1px solid {theme.BORDER};'
                'border-radius:6px;padding:8px;white-space:pre-wrap;"><code>'
                f"{code}</code></pre>"
            )
    return "".join(rendered)


class MessageWidget(QFrame):
    def __init__(self, role: str, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        header = QHBoxLayout()
        name = {"user": "You", "assistant": "JARVIS", "system": "System", "error": "Error"}.get(role, role)
        title = QLabel(name)
        title.setObjectName("H2" if role == "assistant" else "Muted")
        title.setFont(QFont(theme.FONT, 9, QFont.Bold))
        header.addWidget(title)
        header.addStretch(1)
        stamp = QLabel(now_iso()[11:16])
        stamp.setObjectName("Muted")
        stamp.setFont(QFont(theme.FONT, 8))
        header.addWidget(stamp)
        layout.addLayout(header)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setOpenExternalLinks(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.body.setFont(QFont(theme.FONT, 10))
        layout.addWidget(self.body)
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.body.setText(render_markdown(text))

    def mark_error(self) -> None:
        self.setObjectName("Card")
        self.body.setStyleSheet(f"color: {theme.DANGER};")


class ChatPanel(QWidget):
    send_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stream_widget: MessageWidget | None = None
        self._stream_text = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.container.setStyleSheet(f"background: {theme.BG};")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(18, 18, 18, 8)
        self.layout.setSpacing(10)
        self.layout.addStretch(1)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------ messages
    def add_message(self, role: str, text: str = "") -> MessageWidget:
        self.clear_stream()
        widget = MessageWidget(role, text, self.container)
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self._scroll_to_bottom()
        return widget

    def begin_stream(self) -> MessageWidget:
        self.clear_stream()
        self._stream_widget = self.add_message("assistant", "")
        self._stream_text = ""
        return self._stream_widget

    @property
    def has_stream(self) -> bool:
        return self._stream_widget is not None

    def append_stream(self, chunk: str) -> None:
        if self._stream_widget is None:
            self.begin_stream()
        self._stream_text += chunk
        if self._stream_widget is not None:
            self._stream_widget.set_text(self._stream_text)
            self._scroll_to_bottom()

    def end_stream(self) -> str:
        text = self._stream_text
        self._stream_widget = None
        self._stream_text = ""
        return text

    def clear_stream(self) -> None:
        if self._stream_widget is not None:
            self._stream_widget.deleteLater()
            self._stream_widget = None
            self._stream_text = ""

    def clear(self) -> None:
        self.clear_stream()
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def load_history(self, messages: list[dict]) -> None:
        self.clear()
        for message in messages:
            self.add_message(message.get("role", "assistant"), message.get("content", ""))
        self._scroll_to_bottom()

    def show_empty_state(self, suggestions: list[str] | None = None) -> None:
        self.clear()
        intro = MessageWidget(
            "assistant",
            "Systems online. I can talk, control apps and files, search the web, take screenshots on request, "
            "and run multi-step tasks. What would you like to do?",
        )
        self.layout.insertWidget(0, intro)
        for suggestion in suggestions or []:
            row = QFrame()
            row.setObjectName("Card")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            label = QLabel(suggestion)
            label.setObjectName("Muted")
            button = QLabel("Use")
            button.setObjectName("H2")
            button.setCursor(Qt.PointingHandCursor)
            button.mousePressEvent = lambda _event, text=suggestion: self.send_requested.emit(text)
            row_layout.addWidget(label, 1)
            row_layout.addWidget(button)
            self.layout.insertWidget(self.layout.count() - 1, row)

    def _scroll_to_bottom(self) -> None:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._do_scroll)

    def _do_scroll(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())