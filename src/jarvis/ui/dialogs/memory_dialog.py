"""Memory manager: view, add, edit, delete, disable."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.config import AppConfig
from jarvis.memory.store import Store
from jarvis.ui import theme


class MemoryDialog(QDialog):
    memory_changed = Signal()

    def __init__(self, cfg: AppConfig, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.setWindowTitle("Memory")
        self.setModal(True)
        self.resize(720, 520)
        self.setStyleSheet(theme.stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("What JARVIS remembers")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch(1)
        self.enabled = QPushButton("Memory enabled" if cfg.memory_enabled else "Memory disabled")
        self.enabled.setObjectName("Primary" if cfg.memory_enabled else "Ghost")
        self.enabled.clicked.connect(self._toggle_enabled)
        header.addWidget(self.enabled)
        layout.addLayout(header)

        note = QLabel(
            "Only information you approve is stored. Passwords, OTPs, tokens and API keys are rejected automatically."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Type", "Content", "Updated"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(2, 130)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        add = QPushButton("Add", self)
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        edit = QPushButton("Edit", self)
        edit.clicked.connect(self._edit)
        delete = QPushButton("Delete", self)
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        clear = QPushButton("Clear all", self)
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        for button in (add, edit, delete, clear, close):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.reload()

    # -------------------------------------------------------------------- data
    def reload(self) -> None:
        items = self.store.list_memories(limit=500)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item["kind"]))
            content = QTableWidgetItem(item["content"])
            content.setToolTip(item["content"])
            self.table.setItem(row, 1, content)
            self.table.setItem(row, 2, QTableWidgetItem(item["updated_at"][:16].replace("T", " ")))
            self.table.item(row, 0).setData(Qt.UserRole, item["id"])
        self.enabled.setText("Memory enabled" if self.cfg.memory_enabled else "Memory disabled")

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _toggle_enabled(self) -> None:
        self.cfg.memory_enabled = not self.cfg.memory_enabled
        self.reload()
        self.memory_changed.emit()

    def _add(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Add memory", "What should JARVIS remember?")
        if not ok or not text.strip():
            return
        try:
            self.store.add_memory(text.strip(), source="user")
        except ValueError as exc:
            QMessageBox.warning(self, "Not saved", str(exc))
            return
        self.reload()
        self.memory_changed.emit()

    def _edit(self) -> None:
        memory_id = self._selected_id()
        if not memory_id:
            QMessageBox.information(self, "Edit", "Select a memory entry first.")
            return
        current = next((m for m in self.store.list_memories(limit=500) if m["id"] == memory_id), None)
        if not current:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Edit memory", "Memory content", text=current["content"]
        )
        if not ok or not text.strip():
            return
        try:
            self.store.update_memory(memory_id, text.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Not saved", str(exc))
            return
        self.reload()
        self.memory_changed.emit()

    def _delete(self) -> None:
        memory_id = self._selected_id()
        if not memory_id:
            QMessageBox.information(self, "Delete", "Select a memory entry first.")
            return
        confirm = QMessageBox.question(
            self, "Delete memory", "Delete this memory permanently?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.store.delete_memory(memory_id)
            self.reload()
            self.memory_changed.emit()

    def _clear(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear memory", "Delete every stored memory? This cannot be undone.", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.store.clear_memories()
            self.reload()
            self.memory_changed.emit()