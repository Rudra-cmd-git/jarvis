"""Main application window: chat, visualizer, status, tasks and emergency stop."""
from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizeGrip,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from jarvis import __version__
from jarvis.security.permissions import ConfirmationResult
from jarvis.ui import theme
from jarvis.ui.dialogs.confirm_dialog import ConfirmDialog
from jarvis.ui.dialogs.history_dialog import HistoryDialog
from jarvis.ui.dialogs.memory_dialog import MemoryDialog
from jarvis.ui.dialogs.settings_dialog import SettingsDialog
from jarvis.ui.dialogs.workflows_dialog import WorkflowsDialog
from jarvis.ui.widgets.chat_panel import ChatPanel
from jarvis.ui.widgets.input_bar import InputBar
from jarvis.ui.widgets.orb import OrbWidget
from jarvis.ui.widgets.sidebar import Sidebar
from jarvis.ui.widgets.status_panel import StatusPanel
from jarvis.ui.widgets.task_panel import TaskPanel
from jarvis.ui.widgets.toast import ToastHost

logger = logging.getLogger("jarvis.ui")

_STATE_LABEL = {
    "idle": "IDLE",
    "listening": "LISTENING",
    "thinking": "THINKING",
    "working": "WORKING",
    "speaking": "SPEAKING",
    "stopped": "STOPPED",
}

_QUICK_PROMPTS = [
    ("System status", "Give me a quick system status: CPU, RAM, battery and disk."),
    ("Screen help", "Look at my screen and tell me what I should do next."),
    ("Study timer", "Start a 25 minute study timer and block out distractions."),
]


def _make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(theme.CYAN_DARK))
    painter.setPen(QColor(theme.CYAN))
    painter.drawEllipse(6, 6, 52, 52)
    painter.setBrush(QColor(theme.CYAN))
    painter.drawEllipse(24, 24, 16, 16)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.bridge = controller.bridge
        self.cfg = controller.cfg
        self._drag_offset: QPoint | None = None
        self._streaming = False
        self._automation_timer = QTimer(self)
        self._automation_timer.setSingleShot(True)
        self._automation_timer.timeout.connect(lambda: self.status_panel.set_automation(False))

        self.setWindowTitle("J.A.R.V.I.S.")
        self.setWindowIcon(_make_icon())
        self.setMinimumSize(1040, 680)
        self.resize(1320, 840)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"#Root {{ background-color: {theme.BG}; border: 1px solid {theme.BORDER}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self.container = QWidget(self)
        self.container.setObjectName("Root")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        self.container_layout = container_layout
        container_layout.addWidget(self._build_title_bar())
        container_layout.addWidget(self._build_body(), 1)
        container_layout.addWidget(self._build_status_bar())

        self.toasts = ToastHost(self)
        self.toasts.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.toasts.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._position_toasts()

        self._build_tray()
        self._connect()
        self._apply_theme()
        self.refresh_system_panel()
        self.chat.show_empty_state(
            [
                "Give me a system status",
                "Search for my project files",
                "Start a 25 minute study timer",
            ]
        )

        if not controller.api_ready:
            QTimer.singleShot(600, self._prompt_api_setup)

    # ------------------------------------------------------------------ layout
    def _build_title_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setFixedHeight(58)
        bar.setStyleSheet(
            f"QFrame#Card {{ background-color: {theme.BG_ELEVATED}; border: none; border-bottom: 1px solid {theme.BORDER}; border-radius: 0px; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(12)

        brand = QLabel("J.A.R.V.I.S.")
        brand.setObjectName("Brand")
        brand.setFont(QFont(theme.FONT, 15, QFont.Bold))
        layout.addWidget(brand)

        subtitle = QLabel("PERSONAL ASSISTANT")
        subtitle.setObjectName("Muted")
        subtitle.setFont(QFont(theme.FONT, 8))
        layout.addWidget(subtitle)
        layout.addStretch(1)

        self.state_pill = QLabel("● IDLE")
        self.state_pill.setFont(QFont(theme.FONT, 9, QFont.Bold))
        self.state_pill.setStyleSheet(
            f"color: {theme.CYAN}; border: 1px solid {theme.CYAN_DARK}; border-radius: 10px; padding: 4px 10px;"
        )
        layout.addWidget(self.state_pill)

        self.backend_pill = QLabel("")
        self.backend_pill.setObjectName("Muted")
        self.backend_pill.setFont(QFont(theme.FONT, 8))
        layout.addWidget(self.backend_pill)

        self.stop_button = QPushButton("EMERGENCY STOP", bar)
        self.stop_button.setObjectName("Danger")
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.setToolTip("Immediately stop all automation, speech and listening")
        self.stop_button.clicked.connect(self._emergency_stop)
        layout.addWidget(self.stop_button)

        window_button = QPushButton("—", bar)
        window_button.setObjectName("Ghost")
        window_button.setFixedWidth(32)
        window_button.clicked.connect(self.showMinimized)
        layout.addWidget(window_button)

        close_button = QPushButton("✕", bar)
        close_button.setObjectName("Ghost")
        close_button.setFixedWidth(32)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
        return bar

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 0)
        layout.setSpacing(10)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        self.stack = QVBoxLayout()
        self.chat_page = self._build_chat_page()
        self.tasks_page = self._build_tasks_page()
        layout.addLayout(self.stack, 1)
        self.stack.addWidget(self.chat_page)
        self.stack.addWidget(self.tasks_page)
        self.tasks_page.setVisible(False)
        return body

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        column = QVBoxLayout()
        column.setSpacing(10)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(10)

        self.orb = OrbWidget(header, animations=self.cfg.animations and not self.cfg.low_spec)
        self.orb.setFixedSize(176, 176)
        header_layout.addWidget(self.orb)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.state_title = QLabel("Standing by")
        self.state_title.setObjectName("H1")
        self.state_detail = QLabel("Text or voice. Every action is logged.")
        self.state_detail.setObjectName("Muted")
        self.state_detail.setWordWrap(True)
        info.addWidget(self.state_title)
        info.addWidget(self.state_detail)
        info.addStretch(1)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        for label, prompt in _QUICK_PROMPTS:
            button = QPushButton(label, header)
            button.setObjectName("Ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, text=prompt: self.controller.send(text))
            quick.addWidget(button)
        quick.addStretch(1)
        info.addLayout(quick)
        header_layout.addLayout(info, 1)
        column.addWidget(header)

        self.chat = ChatPanel()
        self.chat.send_requested.connect(self.controller.send)
        column.addWidget(self.chat, 1)

        self.input = InputBar()
        self.input.send_requested.connect(self.controller.send)
        self.input.push_to_talk.connect(self._push_to_talk)
        self.input.stop_requested.connect(self.controller.stop)
        self.input.set_voice_enabled(self.cfg.voice_enabled and self.cfg.push_to_talk_enabled)
        column.addWidget(self.input)

        layout.addLayout(column, 1)

        side = QVBoxLayout()
        side.setSpacing(10)
        self.status_panel = StatusPanel()
        side.addWidget(self.status_panel)
        self.mini_task = TaskPanel()
        self.mini_task.setMaximumHeight(300)
        side.addWidget(self.mini_task)
        side.addStretch(1)
        layout.addLayout(side, 0)
        self.side_layout = side
        return page

    def _build_tasks_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.full_task = TaskPanel()
        layout.addWidget(self.full_task)
        return page

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {theme.BG_ELEVATED}; border-top: 1px solid {theme.BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        self.mic_dot = QLabel("MIC OFF")
        self.mic_dot.setFont(QFont(theme.FONT, 8, QFont.Bold))
        self.mic_dot.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(self.mic_dot)

        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setTextVisible(False)
        self.mic_level.setFixedWidth(120)
        self.mic_level.setFixedHeight(5)
        layout.addWidget(self.mic_level)

        layout.addStretch(1)

        self.automation_status = QLabel("Automation: clear")
        self.automation_status.setObjectName("Muted")
        self.automation_status.setFont(QFont(theme.FONT, 8))
        layout.addWidget(self.automation_status)

        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("Muted")
        self.version_label.setFont(QFont(theme.FONT, 8))
        layout.addWidget(self.version_label)

        grip = QSizeGrip(bar)
        layout.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
        return bar

    # ------------------------------------------------------------------- tray
    def _position_toasts(self) -> None:
        margin = 18
        width = 380
        height = 260
        self.toasts.setGeometry(
            max(0, self.width() - width - margin),
            max(0, self.height() - height - margin),
            width,
            height,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_toasts()

    def _build_tray(self) -> None:
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(_make_icon(), self)
        self.tray.setToolTip("J.A.R.V.I.S. is running")
        menu = QMenu()
        show_action = QAction("Open JARVIS", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)
        stop_action = QAction("Emergency stop", self)
        stop_action.triggered.connect(self._emergency_stop)
        menu.addAction(stop_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # --------------------------------------------------------------- connections
    def _connect(self) -> None:
        b = self.bridge
        b.sig_token.connect(self._on_token)
        b.sig_message.connect(self._on_message)
        b.sig_state.connect(self._on_state)
        b.sig_status.connect(self._on_status)
        b.sig_action.connect(self._on_action)
        b.sig_task.connect(self._on_task)
        b.sig_notify.connect(self._on_notify)
        b.sig_error.connect(self._on_error)
        b.sig_listening.connect(self._on_listening)
        b.sig_history.connect(self.chat.load_history)
        b.sig_settings_changed.connect(self._on_settings_changed)
        b.sig_conversation_changed.connect(self._on_conversation_changed)
        b.sig_confirm.connect(self._on_confirm)
        self.sidebar.navigate.connect(self._navigate)

    def _navigate(self, target: str) -> None:
        if target == "settings":
            self._open_settings()
            self.sidebar.set_active("chat")
            return
        if target == "memory":
            dialog = MemoryDialog(self.cfg, self.controller.store, self)
            dialog.memory_changed.connect(self.controller.memory_changed)
            dialog.exec()
            self.sidebar.set_active("chat")
            return
        if target == "history":
            dialog = HistoryDialog(self.controller.store, self)
            dialog.open_conversation.connect(self.controller.load_conversation)
            dialog.exec()
            self.sidebar.set_active("chat")
            return
        if target == "workflows":
            dialog = WorkflowsDialog(self.controller.store, self)
            dialog.run_requested.connect(self._run_workflow)
            dialog.exec()
            self.sidebar.set_active("chat")
            return
        if target == "tasks":
            self.chat_page.setVisible(False)
            self.tasks_page.setVisible(True)
            self.sidebar.set_active("tasks")
            return
        self.chat_page.setVisible(True)
        self.tasks_page.setVisible(False)
        self.sidebar.set_active("chat")

    # ------------------------------------------------------------------ actions
    def _on_token(self, text: str) -> None:
        self._streaming = True
        self.chat.append_stream(text)

    def _on_message(self, message: dict) -> None:
        role = message.get("role", "assistant")
        text = message.get("content", "")
        if role == "assistant":
            if self._streaming and self.chat.has_stream:
                self.chat.end_stream()
            elif text:
                self.chat.add_message("assistant", text)
            self._streaming = False
        elif role == "user":
            self.chat.add_message("user", text)
        elif role == "error":
            self.chat.add_message("error", text)

    def _on_state(self, state: str, detail: str = "") -> None:
        self.orb.set_state(state)
        self.status_panel.set_state(state)
        self.state_pill.setText(f"● {_STATE_LABEL.get(state, state.upper())}")
        colour = {
            "listening": theme.OK,
            "thinking": "#5aa9ff",
            "working": theme.WARN,
            "speaking": theme.CYAN,
            "stopped": theme.DANGER,
        }.get(state, theme.CYAN)
        self.state_pill.setStyleSheet(
            f"color: {colour}; border: 1px solid {colour}; border-radius: 10px; padding: 4px 10px;"
        )
        self.state_title.setText(
            {
                "idle": "Standing by",
                "listening": "Listening",
                "thinking": "Thinking",
                "working": "Working",
                "speaking": "Speaking",
                "stopped": "Stopped",
            }.get(state, state.title())
        )
        self.state_detail.setText(detail or "Text or voice. Every action is logged.")
        self.input.set_busy(state in {"thinking", "working"})
        if state in {"thinking", "working"}:
            self.status_panel.set_automation(True)
            self.automation_status.setText("Automation: ACTIVE")
            self.automation_status.setStyleSheet(f"color: {theme.WARN};")
        elif state == "idle":
            self._automation_timer.start(1500)

    def _on_status(self, text: str) -> None:
        self.state_detail.setText(text)

    def _on_action(self, entry: dict) -> None:
        self.mini_task.add_action(entry)
        self.full_task.add_action(entry)
        self.status_panel.set_automation(True)
        self.automation_status.setText("Automation: ACTIVE")
        self.automation_status.setStyleSheet(f"color: {theme.WARN};")
        self._automation_timer.start(4000)

    def _on_task(self, task: dict) -> None:
        self.mini_task.set_task(task)
        self.full_task.set_task(task)
        if task.get("status") == "done":
            QTimer.singleShot(4000, self.mini_task.clear_task)

    def _on_notify(self, title: str, body: str, level: str = "info") -> None:
        self.toasts.show(title, body, level)
        if getattr(self, "tray_available", False):
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 4000)

    def _on_error(self, text: str) -> None:
        self.toasts.show("Error", text, "error")

    def _on_listening(self, level: float, active: bool) -> None:
        self.orb.set_level(level)
        self.mic_level.setValue(int(level * 100))
        self.input.set_listening(active)
        self.mic_dot.setText("MIC LIVE" if active else "MIC OFF")
        self.mic_dot.setStyleSheet(f"color: {theme.OK if active else theme.MUTED};")

    def _on_settings_changed(self) -> None:
        self.cfg = self.controller.cfg
        self._apply_theme()
        self.input.set_voice_enabled(self.cfg.voice_enabled and self.cfg.push_to_talk_enabled)

    def _on_conversation_changed(self) -> None:
        self.chat.clear()
        self.chat.show_empty_state(["Give me a system status", "Search for my project files", "Start a 25 minute study timer"])

    def _on_confirm(self, request, future) -> None:
        dialog = ConfirmDialog(request, self)
        dialog.exec()
        try:
            future.get_loop().call_soon_threadsafe(future.set_result, dialog.result)
        except Exception:
            logger.exception("Could not deliver confirmation result")

    def _push_to_talk(self, pressed: bool) -> None:
        if pressed:
            self.controller.start_push_to_talk()
        else:
            self.controller.stop_push_to_talk()

    def _emergency_stop(self) -> None:
        self.controller.emergency_stop()
        self.orb.set_state("stopped")
        self.input.set_busy(False)
        self.state_pill.setText("● STOPPED")
        self.state_pill.setStyleSheet(
            f"color: {theme.DANGER}; border: 1px solid {theme.DANGER}; border-radius: 10px; padding: 4px 10px;"
        )
        self.status_panel.set_automation(False)
        self.automation_status.setText("Automation: clear")

    def _run_workflow(self, name: str) -> None:
        self.controller.run_workflow(name)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.cfg,
            self.controller.paths,
            self.controller.secrets,
            self,
            tts=self.controller.tts,
            stt=self.controller.stt,
        )
        dialog.saved.connect(self.controller.apply_settings)
        dialog.exec()

    def _prompt_api_setup(self) -> None:
        result = QMessageBox.question(
            self,
            "Connect an AI provider",
            "No AI provider is configured yet, so JARVIS can chat only with local commands.\n\n"
            "Open Settings > API now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            self._open_settings()

    def _apply_theme(self) -> None:
        self.setStyleSheet(theme.stylesheet(self.cfg.theme_intensity, self.cfg.low_spec))
        self.orb.set_animations(self.cfg.animations and not self.cfg.low_spec)

    def refresh_system_panel(self) -> None:
        if hasattr(self, "status_panel"):
            self.status_panel.refresh()

    # -------------------------------------------------------------- window drag
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() < 58:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None

    # -------------------------------------------------------------------- events
    def closeEvent(self, event) -> None:  # noqa: N802
        if getattr(self, "_force_close", False):
            event.accept()
            return
        if self.cfg.confirm_on_exit:
            result = QMessageBox.question(
                self,
                "Quit JARVIS",
                "Quit JARVIS? Running automation will be stopped.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                event.ignore()
                return
        self.controller.shutdown()
        event.accept()
        QApplication.quit()

    def _quit(self) -> None:
        self._force_close = True
        self.controller.shutdown()
        QApplication.quit()