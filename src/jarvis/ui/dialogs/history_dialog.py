"""Conversation history search."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from jarvis.memory.store import Store
from jarvis.ui import theme


class HistoryDialog(QDialog):
    open_conversation = Signal(str)

    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Conversation history")
        self.setModal(True)
        self.resize(820, 560)
        self.setStyleSheet(theme.stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Search conversations")
        title.setObjectName("H1")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search message text…")
        self.search.textChanged.connect(self._search)
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        body = QHBoxLayout()
        self.results = QListWidget()
        self.results.currentItemChanged.connect(self._preview)
        body.addWidget(self.results, 1)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setFont(QFont(theme.FONT, 10))
        body.addWidget(self.preview, 2)
        layout.addLayout(body, 1)

        buttons = QHBoxLayout()
        open_button = QPushButton("Open conversation", self)
        open_button.setObjectName("Primary")
        open_button.clicked.connect(self._open)
        delete = QPushButton("Delete", self)
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        buttons.addWidget(open_button)
        buttons.addWidget(delete)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._conversation_ids: list[str] = []
        self.reload()

    def reload(self) -> None:
        self._populate(self.store.list_conversations(limit=200))

    def _populate(self, conversations: list[dict]) -> None:
        self.results.clear()
        self._conversation_ids = []
        for conversation in conversations:
            item = QListWidgetItem(
                f"{conversation['title'][:70]}  ·  {conversation['updated_at'][:16].replace('T', ' ')}"
            )
            item.setData(Qt.UserRole, conversation["id"])
            self.results.addItem(item)
            self._conversation_ids.append(conversation["id"])
        if self.results.count():
            self.results.setCurrentRow(0)

    def _search(self, text: str) -> None:
        query = text.strip()
        if not query:
            self.reload()
            return
        rows = self.store.search_messages(query, limit=50)
        seen: set[str] = set()
        conversations = []
        for row in rows:
            cid = row["conversation_id"]
            if cid in seen:
                continue
            seen.add(cid)
            conversations.append(
                {
                    "id": cid,
                    "title": row.get("conversation_title") or "Conversation",
                    "updated_at": row["created_at"],
                }
            )
        self._populate(conversations)

    def _preview(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None = None) -> None:
        if current is None:
            self.preview.clear()
            return
        conversation_id = current.data(Qt.UserRole)
        messages = self.store.list_messages(conversation_id)
        html_parts = []
        for message in messages:
            role = "You" if message["role"] == "user" else "JARVIS"
            html_parts.append(f"<p><b>{role}</b> <span style='color:#7d8ea6'>{message['created_at'][11:16]}</span><br>{_escape(message['content'])}</p>")
        self.preview.setHtml("".join(html_parts) or "<i>No messages</i>")

    def _open(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        conversation_id = item.data(Qt.UserRole)
        self.open_conversation.emit(conversation_id)
        self.accept()

    def _delete(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        self.store.delete_conversation(item.data(Qt.UserRole))
        self.reload()


def _escape(text: str) -> str:
    from html import escape

    return escape(text or "").replace("\n", "<br>")