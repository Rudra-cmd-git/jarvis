"""Optional wake-word listener using a tiny Vosk grammar.

Only listens while explicitly enabled. Audio is never stored or uploaded.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable

from jarvis.voice.audio import SAMPLE_RATE, _dbfs, _rms
from jarvis.voice.models import find_model

logger = logging.getLogger("jarvis.voice.wakeword")


class WakeWordListener:
    def __init__(
        self,
        model_dir,
        wake_word: str = "jarvis",
        on_detected: Callable[[], None] | None = None,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self.model_dir = model_dir
        self.wake_word = wake_word.strip().lower() or "jarvis"
        self.on_detected = on_detected
        self.on_level = on_level
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False

    def available(self) -> tuple[bool, str]:
        if find_model(self.model_dir) is None:
            return False, "Vosk model not downloaded yet"
        return True, f"Wake word: '{self.wake_word}'"

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="jarvis-wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _run(self) -> None:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model, SetLogLevel

        model_path = find_model(self.model_dir)
        if model_path is None:
            logger.warning("Wake word disabled: no Vosk model")
            self._running = False
            return
        SetLogLevel(-1)
        model = Model(str(model_path))
        grammar = json.dumps([self.wake_word, "hey " + self.wake_word, "[unk]"])
        recognizer = KaldiRecognizer(model, SAMPLE_RATE, grammar)
        recognizer.SetWords(False)

        block = int(SAMPLE_RATE * 0.1) * 2
        last_level_emit = 0.0

        def callback(indata, _frames, _time, status) -> None:
            if status:
                logger.debug("Wake word audio status: %s", status)
            data = bytes(indata)
            level = _dbfs(_rms(data))
            if self.on_level and time.monotonic() - last_level_emit > 0.08:
                last_level_emit = time.monotonic()
                self.on_level(max(0.0, min(1.0, (level + 60.0) / 60.0)))
            if level < -50.0:
                return
            if recognizer.AcceptWaveform(data):
                text = json.loads(recognizer.Result()).get("text", "").strip().lower()
                if self.wake_word in text:
                    self._fire()

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block // 2, callback=callback
            ):
                while not self._stop.is_set():
                    time.sleep(0.1)
        except Exception as exc:
            logger.warning("Wake word listener stopped: %s", exc)
        finally:
            self._running = False

    def _fire(self) -> None:
        logger.info("Wake word detected")
        if self.on_detected:
            try:
                self.on_detected()
            except Exception:
                logger.exception("Wake word callback failed")