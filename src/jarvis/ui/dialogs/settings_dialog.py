"""Settings: general, API, voice, security and appearance."""
from __future__ import annotations

import asyncio
import threading
import traceback

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.ai.client import ChatClient
from jarvis.ai.providers import PROVIDERS, get_preset, resolve_endpoint
from jarvis.config import AppConfig, AppPaths, save_config
from jarvis.core.util import truncate
from jarvis.security.secrets import SecretStore
from jarvis.ui import theme
from jarvis.voice.audio import MicRecorder, default_input_index
from jarvis.voice.models import ensure_model, find_model
from jarvis.voice.stt import SpeechToText
from jarvis.voice.tts import TextToSpeech


def _scroll_area(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(inner)
    return area


class SettingsDialog(QDialog):
    saved = Signal(object)
    test_status_signal = Signal(str, str)
    model_ready_signal = Signal()

    def __init__(
        self,
        cfg: AppConfig,
        paths: AppPaths,
        secrets: SecretStore,
        parent: QWidget | None = None,
        tts: TextToSpeech | None = None,
        stt: SpeechToText | None = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.paths = paths
        self.secrets = secrets
        self.tts = tts
        self.stt = stt
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(860, 640)
        self.setStyleSheet(theme.stylesheet())
        self.test_status_signal.connect(self._apply_test_status)
        self.model_ready_signal.connect(self._refresh_model_status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll_area(self._build_general()), "General")
        self.tabs.addTab(_scroll_area(self._build_api()), "API")
        self.tabs.addTab(_scroll_area(self._build_voice()), "Voice")
        self.tabs.addTab(_scroll_area(self._build_security()), "Security")
        self.tabs.addTab(_scroll_area(self._build_appearance()), "Appearance")
        self.tabs.addTab(_scroll_area(self._build_about()), "About")
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(16, 10, 16, 14)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        footer.addWidget(self.status, 1)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save settings", self)
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(save)
        layout.addLayout(footer)

    # ------------------------------------------------------------------ general
    def _build_general(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        self.name = QLineEdit(self.cfg.assistant_name)
        form.addRow("Assistant name", self.name)

        self.personality = QPlainTextEdit(self.cfg.personality)
        self.personality.setFixedHeight(100)
        form.addRow("Personality", self.personality)

        self.language = QComboBox()
        self.language.addItems(["auto", "english", "hinglish"])
        self.language.setCurrentText(self.cfg.language)
        form.addRow("Language", self.language)

        self.style = QComboBox()
        self.style.addItems(["concise", "detailed"])
        self.style.setCurrentText(self.cfg.response_style)
        form.addRow("Response style", self.style)

        self.agent_mode = QCheckBox("Agent mode: plan and execute multi-step tasks")
        self.agent_mode.setChecked(self.cfg.agent_mode)
        form.addRow("Behaviour", self.agent_mode)

        self.max_iterations = QSpinBox()
        self.max_iterations.setRange(1, 25)
        self.max_iterations.setValue(self.cfg.max_tool_iterations)
        form.addRow("Max tool iterations", self.max_iterations)

        self.history_limit = QSpinBox()
        self.history_limit.setRange(2, 100)
        self.history_limit.setValue(self.cfg.history_limit)
        form.addRow("Remembered messages", self.history_limit)
        return page

    # ---------------------------------------------------------------------- api
    def _build_api(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        note = QLabel(
            "DeepSeek and OpenRouter both expose an OpenAI-compatible API. Keys are encrypted with Windows DPAPI "
            "and stored outside the project folder. You can also put keys in .env (see .env.example)."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        form.addRow(note)

        self.provider = QComboBox()
        for provider_id, preset in PROVIDERS.items():
            self.provider.addItem(f"{preset.label} ({provider_id})", provider_id)
        index = self.provider.findData(self.cfg.provider)
        self.provider.setCurrentIndex(max(0, index))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        form.addRow("Provider", self.provider)

        self.base_url = QLineEdit(self.cfg.base_url)
        self.base_url.setPlaceholderText(get_preset(self.cfg.provider).base_url or "http://127.0.0.1:11434/v1")
        form.addRow("API base URL", self.base_url)

        self.model = QLineEdit(self.cfg.model)
        self.model.setPlaceholderText(get_preset(self.cfg.provider).default_model or "model-name")
        form.addRow("Model", self.model)

        key_row = QHBoxLayout()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText(
            "Saved securely" if self.secrets.provider_key(self.cfg.provider) else "Not configured"
        )
        show = QPushButton("Show", self)
        show.setObjectName("Ghost")
        show.setCheckable(True)
        show.toggled.connect(lambda checked: self.api_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password))
        clear = QPushButton("Clear key", self)
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear_key)
        key_row.addWidget(self.api_key, 1)
        key_row.addWidget(show)
        key_row.addWidget(clear)
        form.addRow("API key", key_row)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test connection", self)
        self.test_button.setObjectName("Primary")
        self.test_button.clicked.connect(self._test_connection)
        self.test_status = QLabel("")
        self.test_status.setObjectName("Muted")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_status, 1)
        form.addRow("", test_row)

        self.temperature = QSpinBox()
        self.temperature.setRange(0, 200)
        self.temperature.setValue(int(self.cfg.temperature * 100))
        self.temperature.setSuffix(" / 100")
        form.addRow("Temperature", self.temperature)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(64, 8192)
        self.max_tokens.setValue(self.cfg.max_tokens)
        form.addRow("Max response tokens", self.max_tokens)

        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setValue(int(self.cfg.request_timeout))
        self.timeout.setSuffix(" s")
        form.addRow("Request timeout", self.timeout)
        return page

    def _provider_changed(self) -> None:
        preset = get_preset(self.provider.currentData())
        if not self.base_url.text().strip():
            self.base_url.setPlaceholderText(preset.base_url or "http://127.0.0.1:11434/v1")
        self.model.setPlaceholderText(preset.default_model or "model-name")
        self.api_key.clear()
        self.api_key.setPlaceholderText(
            "Saved securely" if self.secrets.provider_key(preset.id) else "Not configured"
        )

    def _clear_key(self) -> None:
        self.secrets.delete(self.secrets.key_for_provider(self.provider.currentData()))
        self.api_key.clear()
        self.api_key.setPlaceholderText("Not configured")

    def _collect_api(self) -> AppConfig:
        cfg = self._collect()
        cfg.provider = self.provider.currentData()
        cfg.base_url = self.base_url.text().strip()
        cfg.model = self.model.text().strip()
        cfg.temperature = self.temperature.value() / 100.0
        cfg.max_tokens = self.max_tokens.value()
        cfg.request_timeout = float(self.timeout.value())
        return cfg

    def _test_connection(self) -> None:
        cfg = self._collect_api()
        if self.api_key.text().strip():
            self.secrets.store_provider_key(cfg.provider, self.api_key.text().strip())
        self.test_button.setEnabled(False)
        self.test_status.setText("Testing…")

        def worker() -> None:
            try:
                endpoint = resolve_endpoint(cfg, self.secrets)
                client = ChatClient(endpoint, timeout=min(30.0, cfg.request_timeout))

                async def run() -> str:
                    try:
                        result = await client.complete(
                            [{"role": "user", "content": "Reply with the single word: ready"}],
                            max_tokens=16,
                            temperature=0,
                        )
                        return f"Connected to {endpoint.provider}/{endpoint.model}. Reply: {result.text.strip()!r}"
                    finally:
                        await client.close()

                message = asyncio.run(run())
                level = "ok"
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                level = "error"
            self._set_test_status(message, level)

        threading.Thread(target=worker, daemon=True).start()

    def _set_test_status(self, message: str, level: str) -> None:
        # May be called from a worker thread; the signal is queued to the GUI thread.
        self.test_status_signal.emit(message, level)

    def _apply_test_status(self, message: str, level: str) -> None:
        self.test_button.setEnabled(True)
        self.test_status.setText(message)
        self.test_status.setStyleSheet(
            f"color: {theme.OK};" if level == "ok" else f"color: {theme.DANGER};"
        )

    # -------------------------------------------------------------------- voice
    def _build_voice(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        self.voice_enabled = QCheckBox("Enable spoken replies")
        self.voice_enabled.setChecked(self.cfg.voice_enabled)
        form.addRow("Text to speech", self.voice_enabled)

        self.tts_voice = QComboBox()
        self._populate_voices()
        form.addRow("Voice", self.tts_voice)

        self.rate = QSpinBox()
        self.rate.setRange(-50, 100)
        self.rate.setValue(self.cfg.tts_rate)
        form.addRow("Speaking rate", self.rate)

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(self.cfg.tts_volume * 100))
        form.addRow("Speaking volume", self.volume)

        test_voice = QPushButton("Test voice", self)
        test_voice.setObjectName("Primary")
        test_voice.clicked.connect(self._test_voice)
        form.addRow("", test_voice)

        self.stt_backend = QComboBox()
        self.stt_backend.addItem("Vosk (offline, free)", "vosk")
        self.stt_backend.addItem("Google Web Speech (online, free)", "google")
        index = self.stt_backend.findData(self.cfg.stt_backend)
        self.stt_backend.setCurrentIndex(max(0, index))
        self.stt_backend.currentIndexChanged.connect(self._stt_changed)
        form.addRow("Speech to text", self.stt_backend)

        model_row = QHBoxLayout()
        self.model_status = QLabel("")
        self.model_status.setObjectName("Muted")
        self.model_status.setWordWrap(True)
        download = QPushButton("Download voice model", self)
        download.setObjectName("Primary")
        download.clicked.connect(self._download_model)
        model_row.addWidget(self.model_status, 1)
        model_row.addWidget(download)
        form.addRow("Vosk model", model_row)

        mic_row = QHBoxLayout()
        self.mic_status = QLabel("")
        self.mic_status.setObjectName("Muted")
        test_mic = QPushButton("Test microphone", self)
        test_mic.setObjectName("Primary")
        test_mic.clicked.connect(self._test_mic)
        mic_row.addWidget(self.mic_status, 1)
        mic_row.addWidget(test_mic)
        form.addRow("Microphone", mic_row)

        self.push_to_talk = QCheckBox("Push-to-talk (hold the mic button)")
        self.push_to_talk.setChecked(self.cfg.push_to_talk_enabled)
        form.addRow("Push to talk", self.push_to_talk)

        self.wake_enabled = QCheckBox("Wake word (experimental, listens only while enabled)")
        self.wake_enabled.setChecked(self.cfg.wake_word_enabled)
        form.addRow("Wake word", self.wake_enabled)

        self.wake_word = QLineEdit(self.cfg.wake_word)
        form.addRow("Wake word", self.wake_word)

        self._refresh_model_status()
        return page

    def _populate_voices(self) -> None:
        self.tts_voice.clear()
        voices = []
        try:
            engine = TextToSpeech()
            voices = engine.list_voices()
        except Exception:  # pragma: no cover - depends on SAPI
            pass
        for voice in voices:
            self.tts_voice.addItem(f"{voice['name']} ({voice.get('gender') or 'unknown'})", voice["id"])
        current = self.tts_voice.findData(self.cfg.tts_voice)
        if current >= 0:
            self.tts_voice.setCurrentIndex(current)

    def _refresh_model_status(self) -> None:
        model = find_model(self.paths.models_dir)
        if model:
            self.model_status.setText(f"Installed: {model.name}")
            self.model_status.setStyleSheet(f"color: {theme.OK};")
        else:
            self.model_status.setText("Not downloaded. About 40 MB, downloaded once.")
            self.model_status.setStyleSheet(f"color: {theme.MUTED};")

    def _stt_changed(self) -> None:
        self._refresh_model_status()

    def _download_model(self) -> None:
        self.model_status.setText("Downloading…")
        self.model_status.setStyleSheet(f"color: {theme.WARN};")

        def worker() -> None:
            try:
                model = ensure_model(self.paths.models_dir, allow_download=True)
                message = f"Installed: {model.name}" if model else "Download failed. Check your connection."
                level = "ok" if model else "error"
            except Exception as exc:  # noqa: BLE001
                message = f"Download failed: {exc}"
                level = "error"
            self._set_test_status(message, level)
            self.model_ready_signal.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _test_voice(self) -> None:
        voice = TextToSpeech(
            voice_name=self.tts_voice.currentData() or "",
            rate=self.rate.value(),
            volume=self.volume.value() / 100.0,
        )
        voice.speak("All systems nominal. Voice interface online.", interrupt=True)

    def _test_mic(self) -> None:
        backend = self.stt_backend.currentData()
        stt = SpeechToText(backend=backend, model_dir=self.paths.models_dir)
        available, detail = stt.available()
        if not available:
            self.mic_status.setText(detail)
            self.mic_status.setStyleSheet(f"color: {theme.DANGER};")
            return
        self.mic_status.setText("Listening for 3 seconds… speak now.")
        self.mic_status.setStyleSheet(f"color: {theme.WARN};")

        def worker() -> None:
            recorder = MicRecorder()
            pcm = recorder.record_seconds(3.0, vad=True)
            if not pcm:
                message = "No speech detected. Check the microphone and Windows privacy settings."
            else:
                result = stt.transcribe(pcm)
                message = result.text if result.text else f"Transcription failed: {result.error}"
            self._set_test_status(message, "ok" if pcm else "error")
            if backend == "vosk":
                self.model_ready_signal.emit()

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------------------------------------------- security
    def _build_security(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        self.confirm_medium = QCheckBox("Ask before medium-risk actions (file changes, downloads)")
        self.confirm_medium.setChecked(self.cfg.confirm_medium)
        form.addRow("Confirmations", self.confirm_medium)

        self.allow_high = QCheckBox("Allow high-risk actions after explicit confirmation")
        self.allow_high.setChecked(self.cfg.allow_high_risk)
        form.addRow("High-risk actions", self.allow_high)

        warning = QLabel(
            "High-risk actions include Recycle Bin deletion, shutdown/restart, emptying the Recycle Bin and "
            "clearing all memory. They always require explicit confirmation and are never run in the background."
        )
        warning.setObjectName("Muted")
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {theme.WARN};")
        form.addRow(warning)

        self.roots = QListWidget()
        self.roots.addItems(self.cfg.allowed_roots)
        form.addRow("Allowed folders", self.roots)

        root_buttons = QHBoxLayout()
        add = QPushButton("Add folder", self)
        add.clicked.connect(self._add_root)
        remove = QPushButton("Remove", self)
        remove.setObjectName("Ghost")
        remove.clicked.connect(self._remove_root)
        root_buttons.addWidget(add)
        root_buttons.addWidget(remove)
        root_buttons.addStretch(1)
        form.addRow("", root_buttons)

        matrix = QLabel(
            "LOW RISK: answer questions, open apps, search files, read documents, volume.\n"
            "MEDIUM RISK: create/edit/move files, downloads, typing, sending messages.\n"
            "HIGH RISK: permanent deletion, registry, installing software, admin commands, credentials."
        )
        matrix.setFont(QFont(theme.MONO, 8))
        matrix.setWordWrap(True)
        matrix.setStyleSheet(f"color: {theme.MUTED};")
        form.addRow("Risk policy", matrix)
        return page

    def _add_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose an allowed folder")
        if not folder:
            return
        if folder not in self.cfg.allowed_roots:
            self.roots.addItem(folder)

    def _remove_root(self) -> None:
        item = self.roots.currentItem()
        if item is not None:
            self.roots.takeItem(self.roots.row(item))

    # --------------------------------------------------------------- appearance
    def _build_appearance(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        self.animations = QCheckBox("Enable animations")
        self.animations.setChecked(self.cfg.animations)
        form.addRow("Animations", self.animations)

        self.low_spec = QCheckBox("Low-spec mode (reduce glow and animation rate)")
        self.low_spec.setChecked(self.cfg.low_spec)
        form.addRow("Performance", self.low_spec)

        self.intensity = QSlider(Qt.Horizontal)
        self.intensity.setRange(30, 150)
        self.intensity.setValue(int(self.cfg.theme_intensity * 100))
        form.addRow("Accent intensity (%)", self.intensity)

        self.start_minimized = QCheckBox("Start minimized to tray")
        self.start_minimized.setChecked(self.cfg.start_minimized)
        form.addRow("Startup", self.start_minimized)

        self.confirm_exit = QCheckBox("Ask for confirmation before quitting")
        self.confirm_exit.setChecked(self.cfg.confirm_on_exit)
        form.addRow("Exit", self.confirm_exit)
        return page

    # -------------------------------------------------------------------- about
    def _build_about(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        from jarvis import __version__

        title = QLabel(f"J.A.R.V.I.S. {__version__}")
        title.setObjectName("H1")
        layout.addWidget(title)
        body = QLabel(
            "An original local-first Windows assistant. It is not affiliated with Marvel or Disney, and ships "
            "no copyrighted assets or voice recordings.\n\n"
            f"Config: {self.paths.config_file}\n"
            f"Database: {self.paths.database_file}\n"
            f"Logs: {self.paths.log_dir}\n"
            f"Screenshots: {self.paths.screenshot_dir}\n\n"
            "Your API keys never appear in logs, chat history or memory. Screen capture happens only on explicit request."
        )
        body.setWordWrap(True)
        body.setFont(QFont(theme.FONT, 10))
        layout.addWidget(body)
        layout.addStretch(1)
        return page

    # --------------------------------------------------------------------- save
    def _collect(self) -> AppConfig:
        cfg = AppConfig.from_dict(self.cfg.to_dict())
        cfg.assistant_name = self.name.text().strip() or "JARVIS"
        cfg.personality = self.personality.toPlainText().strip()
        cfg.language = self.language.currentText()
        cfg.response_style = self.style.currentText()
        cfg.agent_mode = self.agent_mode.isChecked()
        cfg.max_tool_iterations = self.max_iterations.value()
        cfg.history_limit = self.history_limit.value()
        cfg.voice_enabled = self.voice_enabled.isChecked()
        cfg.tts_voice = self.tts_voice.currentData() or ""
        cfg.tts_rate = self.rate.value()
        cfg.tts_volume = self.volume.value() / 100.0
        cfg.stt_backend = self.stt_backend.currentData() or "vosk"
        cfg.push_to_talk_enabled = self.push_to_talk.isChecked()
        cfg.wake_word_enabled = self.wake_enabled.isChecked()
        cfg.wake_word = self.wake_word.text().strip() or "jarvis"
        cfg.confirm_medium = self.confirm_medium.isChecked()
        cfg.allow_high_risk = self.allow_high.isChecked()
        cfg.allowed_roots = [self.roots.item(i).text() for i in range(self.roots.count())]
        cfg.animations = self.animations.isChecked()
        cfg.low_spec = self.low_spec.isChecked()
        cfg.theme_intensity = self.intensity.value() / 100.0
        cfg.start_minimized = self.start_minimized.isChecked()
        cfg.confirm_on_exit = self.confirm_exit.isChecked()
        return cfg

    def _save(self) -> None:
        cfg = self._collect_api()
        problems = cfg.validate()
        if problems:
            QMessageBox.warning(self, "Check settings", "\n".join(problems))
            return
        if self.api_key.text().strip():
            if not self.secrets.store_provider_key(cfg.provider, self.api_key.text().strip()):
                QMessageBox.warning(
                    self,
                    "Key not saved",
                    "Windows DPAPI is unavailable, so the key was not encrypted.\n"
                    "Put it in .env instead (see .env.example).",
                )
        save_config(cfg, self.paths)
        self.saved.emit(cfg)
        self.accept()