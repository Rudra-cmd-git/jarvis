"""Text-to-speech using the built-in Windows SAPI voices (offline, free)."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

logger = logging.getLogger("jarvis.voice.tts")


class TextToSpeech:
    def __init__(
        self,
        voice_name: str = "",
        rate: int = 0,
        volume: float = 1.0,
        on_state: Callable[[str], None] | None = None,
    ) -> None:
        self.voice_name = voice_name
        self.rate = rate
        self.volume = volume
        self.on_state = on_state
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._engine = None
        self._stop = threading.Event()
        self._speaking = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public
    def available(self) -> tuple[bool, str]:
        try:
            voices = self.list_voices()
        except Exception as exc:
            return False, str(exc)
        if not voices:
            return False, "No SAPI voices were found on this system"
        return True, f"{len(voices)} SAPI voices available"

    def list_voices(self) -> list[dict]:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            voices = []
            for index, voice in enumerate(engine.getProperty("voices")):
                voices.append(
                    {
                        "id": voice.id,
                        "name": voice.name,
                        "languages": list(getattr(voice, "languages", []) or []),
                        "gender": getattr(voice, "gender", ""),
                        "index": index,
                    }
                )
            return voices
        finally:
            try:
                engine.stop()
            except Exception:
                pass

    def configure(self, voice_name: str = "", rate: int = 0, volume: float = 1.0) -> None:
        self.voice_name = voice_name
        self.rate = rate
        self.volume = volume
        self._apply_settings()

    def speak(self, text: str, interrupt: bool = False) -> None:
        text = (text or "").strip()
        if not text:
            return
        if interrupt:
            self.stop()
        self._ensure_started()
        self._queue.put(text)

    def stop(self) -> None:
        self._stop.set()
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def shutdown(self) -> None:
        self._queue.put(None)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._engine = None

    @property
    def speaking(self) -> bool:
        return self._speaking

    # ----------------------------------------------------------------- private
    def _ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-tts", daemon=True)
        self._thread.start()

    def _apply_settings(self) -> None:
        engine = self._engine
        if engine is None:
            return
        try:
            engine.setProperty("rate", int(self.rate))
            engine.setProperty("volume", max(0.0, min(1.0, float(self.volume))))
            if self.voice_name:
                for voice in engine.getProperty("voices"):
                    if self.voice_name.lower() in voice.name.lower() or voice.id == self.voice_name:
                        engine.setProperty("voice", voice.id)
                        break
        except Exception:
            logger.exception("Could not apply TTS settings")

    def _run(self) -> None:
        import pyttsx3

        try:
            self._engine = pyttsx3.init()
        except Exception as exc:
            logger.error("Text-to-speech unavailable: %s", exc)
            return
        self._apply_settings()
        while True:
            item = self._queue.get()
            if item is None:
                break
            self._stop.clear()
            with self._lock:
                self._speaking = True
                if self.on_state:
                    self.on_state("speaking")
            try:
                self._engine.say(item)
                self._engine.runAndWait()
            except Exception as exc:
                logger.warning("TTS playback failed: %s", exc)
            finally:
                with self._lock:
                    self._speaking = False
                if self.on_state:
                    self.on_state("idle")
        try:
            self._engine.stop()
        except Exception:
            pass