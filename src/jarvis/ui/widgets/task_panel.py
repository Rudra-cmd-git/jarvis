"""Active task and transparent action log."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import theme


class TaskPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("ACTIVE TASK")
        title.setObjectName("H2")
        layout.addWidget(title)

        self.task_label = QLabel("No active task")
        self.task_label.setWordWrap(True)
        self.task_label.setFont(QFont(theme.FONT, 10))
        layout.addWidget(self.task_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        self.detail.setFont(QFont(theme.FONT, 8))
        layout.addWidget(self.detail)

        actions_header = QHBoxLayout()
        log_title = QLabel("ACTION LOG")
        log_title.setObjectName("Muted")
        log_title.setFont(QFont(theme.FONT, 8))
        actions_header.addWidget(log_title)
        actions_header.addStretch(1)
        layout.addLayout(actions_header)

        self.log = QListWidget()
        self.log.setWordWrap(True)
        self.log.setFont(QFont(theme.FONT, 8))
        layout.addWidget(self.log, 1)

    def set_task(self, task: dict) -> None:
        status = task.get("status", "running")
        title = task.get("title", "Task")
        if status == "running":
            step = task.get("step", 1)
            total = task.get("total", 1)
            self.task_label.setText(f"{title}  ·  step {step}/{total}")
            self.progress.setVisible(True)
            self.progress.setValue(int(step / max(1, total) * 100))
            self.detail.setText(f"Running: {task.get('tool', '')}")
        elif status == "done":
            succeeded = task.get("succeeded", 0)
            failed = task.get("failed", 0)
            self.task_label.setText(f"{title} complete")
            self.progress.setValue(100)
            self.detail.setText(f"{succeeded} succeeded · {failed} failed")
        else:
            self.task_label.setText(str(title))

    def clear_task(self) -> None:
        self.task_label.setText("No active task")
        self.progress.setVisible(False)
        self.detail.setText("")

    def add_action(self, entry: dict) -> None:
        ok = entry.get("ok", True)
        marker = "✓" if ok else "✕"
        stamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"{marker} {stamp}  {entry.get('summary', '')}")
        self.log.insertItem(0, item)
        while self.log.count() > 60:
            self.log.takeItem(self.log.count() - 1)

    def load_actions(self, actions: list[dict]) -> None:
        self.log.clear()
        for entry in actions[:60]:
            ok = bool(entry.get("ok"))
            marker = "✓" if ok else "✕"
            stamp = (entry.get("created_at") or "")[11:19]
            self.log.addItem(f"{marker} {stamp}  {entry.get('summary', '')}")