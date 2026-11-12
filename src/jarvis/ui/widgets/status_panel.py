"""Live system status: CPU, RAM, disk, battery and backend state."""
from __future__ import annotations

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from jarvis.ui import theme


class _Stat(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardAlt")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        header = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("Muted")
        self.title.setFont(QFont(theme.FONT, 8))
        self.value = QLabel("—")
        self.value.setFont(QFont(theme.FONT, 10, QFont.Bold))
        self.value.setAlignment(Qt.AlignRight)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.value)
        layout.addLayout(header)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)


class StatusPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("SYSTEM")
        title.setObjectName("H2")
        layout.addWidget(title)

        self.cpu = _Stat("CPU", self)
        self.memory = _Stat("RAM", self)
        self.disk = _Stat("DISK", self)
        self.battery = _Stat("BATTERY", self)
        for stat in (self.cpu, self.memory, self.disk, self.battery):
            layout.addWidget(stat)

        line = QFrame()
        line.setObjectName("Divider")
        layout.addWidget(line)

        self.state_label = QLabel("JARVIS idle")
        self.state_label.setObjectName("Muted")
        layout.addWidget(self.state_label)

        self.backend_label = QLabel("Backend: starting…")
        self.backend_label.setObjectName("Muted")
        self.backend_label.setWordWrap(True)
        layout.addWidget(self.backend_label)

        self.automation_label = QLabel("Automation: clear")
        self.automation_label.setObjectName("Muted")
        layout.addWidget(self.automation_label)
        layout.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2500)
        self.refresh()

    def refresh(self) -> None:
        try:
            cpu = psutil.cpu_percent(interval=None)
            self.cpu.value.setText(f"{cpu:.0f}%")
            self.cpu.bar.setValue(int(cpu))
        except Exception:
            pass
        try:
            memory = psutil.virtual_memory()
            self.memory.value.setText(f"{memory.percent:.0f}%")
            self.memory.bar.setValue(int(memory.percent))
        except Exception:
            pass
        try:
            disk = psutil.disk_usage("C:\\")
            self.disk.value.setText(f"{disk.percent:.0f}%")
            self.disk.bar.setValue(int(disk.percent))
        except Exception:
            pass
        try:
            battery = psutil.sensors_battery()
            if battery:
                self.battery.value.setText(f"{battery.percent:.0f}%")
                self.battery.bar.setValue(int(battery.percent))
            else:
                self.battery.value.setText("AC")
                self.battery.bar.setValue(100)
        except Exception:
            pass

    def set_state(self, state: str) -> None:
        label = {
            "idle": "JARVIS idle",
            "listening": "JARVIS listening",
            "thinking": "JARVIS thinking",
            "working": "JARVIS working",
            "speaking": "JARVIS speaking",
            "stopped": "JARVIS stopped",
        }.get(state, f"JARVIS {state}")
        self.state_label.setText(label)
        colour = {
            "listening": theme.OK,
            "thinking": "#5aa9ff",
            "working": theme.WARN,
            "stopped": theme.DANGER,
        }.get(state, theme.MUTED)
        self.state_label.setStyleSheet(f"color: {colour};")

    def set_backend(self, text: str) -> None:
        self.backend_label.setText(text)

    def set_automation(self, active: bool) -> None:
        self.automation_label.setText("Automation: ACTIVE" if active else "Automation: clear")
        self.automation_label.setStyleSheet(
            f"color: {theme.WARN};" if active else f"color: {theme.MUTED};"
        )