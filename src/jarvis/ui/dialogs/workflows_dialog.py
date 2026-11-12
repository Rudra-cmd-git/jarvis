"""Workflow builder and runner."""
from __future__ import annotations

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.memory.store import Store
from jarvis.ui import theme


class WorkflowsDialog(QDialog):
    run_requested = Signal(str)

    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Workflows")
        self.setModal(True)
        self.resize(760, 540)
        self.setStyleSheet(theme.stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Reusable automation")
        title.setObjectName("H1")
        layout.addWidget(title)
        hint = QLabel(
            'A workflow is a sequence of tool calls, e.g. [{"tool":"open_app","args":{"name":"chrome"}}]. '
            "Each step asks for confirmation where the risk level requires it."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._preview)
        layout.addWidget(self.list, 1)

        self.steps = QPlainTextEdit()
        self.steps.setPlaceholderText('[\n  {"tool": "open_app", "args": {"name": "chrome"}},\n  {"tool": "open_url", "args": {"url": "https://youtube.com"}}\n]')
        self.steps.setFixedHeight(120)
        self.steps.setFont(QFont("Consolas", 9))
        self.steps.setVisible(False)
        layout.addWidget(self.steps)

        form = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Workflow name, e.g. Study Mode")
        form.addWidget(self.name, 1)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save = QPushButton("Save workflow", self)
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        run = QPushButton("Run", self)
        run.clicked.connect(self._run)
        delete = QPushButton("Delete", self)
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        for button in (save, run, delete, close):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for workflow in self.store.list_workflows():
            steps = json.loads(workflow.get("steps_json") or "[]")
            item = QListWidgetItem(f"{workflow['name']}  ·  {len(steps)} steps")
            item.setData(Qt.UserRole, workflow["name"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _preview(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        name = current.data(Qt.UserRole)
        workflow = self.store.get_workflow(name)
        if workflow:
            self.name.setText(workflow["name"])
            self.steps.setPlainText(json.dumps(workflow.get("steps", []), indent=2))
            self.steps.setVisible(True)

    def _save(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.information(self, "Save", "Enter a workflow name.")
            return
        try:
            steps = json.loads(self.steps.toPlainText() or "[]")
            if not isinstance(steps, list) or not steps:
                raise ValueError("steps must be a non-empty JSON array")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid steps", str(exc))
            return
        self.store.save_workflow(name, "", steps)
        self.reload()

    def _run(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.information(self, "Run", "Select or enter a workflow name.")
            return
        if self.store.get_workflow(name) is None:
            QMessageBox.information(self, "Run", f"No saved workflow named '{name}'.")
            return
        self.run_requested.emit(name)
        self.accept()

    def _delete(self) -> None:
        name = self.name.text().strip()
        if not name or self.store.get_workflow(name) is None:
            QMessageBox.information(self, "Delete", "Select a saved workflow first.")
            return
        self.store.delete_workflow(name)
        self.reload()