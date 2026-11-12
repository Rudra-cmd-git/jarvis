"""Speech-to-text backends.

Primary: Vosk (offline, free, no API key).
Fallback: Google Web Speech (free, requires internet, better Hinglish than the
small English model, but it is a network service and can rate-limit).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from jarvis.voice.audio import SAMPLE_RATE
from jarvis.voice.models import ensure_model, find_model

logger = logging.getLogger("jarvis.voice.stt")


@dataclass
class Transcription:
    text: str
    backend: str
    error: str = ""


class SpeechToText:
    def __init__(self, backend: str = "vosk", model_dir: Path | None = None, language: str = "en-IN") -> None:
        self.backend = backend
        self.model_dir = model_dir
        self.language = language
        self._model = None
        self._model_path: Path | None = None

    # ------------------------------------------------------------------ public
    def available(self) -> tuple[bool, str]:
        if self.backend == "vosk":
            path = find_model(self.model_dir) if self.model_dir else None
            if path is None:
                return False, "Vosk model not downloaded yet. Use 'Download voice model' in Settings > Voice."
            return True, str(path)
        if self.backend == "google":
            return True, "Google Web Speech (requires internet)"
        return False, f"Unknown speech backend '{self.backend}'"

    def load(self) -> None:
        if self.backend != "vosk":
            return
        if self._model is not None:
            return
        path = find_model(self.model_dir) if self.model_dir else None
        if path is None:
            raise RuntimeError("Vosk model is not installed")
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        self._model = Model(str(path))
        self._model_path = path

    def transcribe(self, pcm: bytes) -> Transcription:
        if not pcm:
            return Transcription("", self.backend, "No audio captured")
        try:
            if self.backend == "vosk":
                return self._transcribe_vosk(pcm)
            if self.backend == "google":
                return self._transcribe_google(pcm)
            return Transcription("", self.backend, f"Unknown backend '{self.backend}'")
        except Exception as exc:  # noqa: BLE001 - never crash the voice loop
            logger.warning("Transcription failed (%s): %s", self.backend, exc)
            return Transcription("", self.backend, str(exc))

    # ----------------------------------------------------------------- private
    def _transcribe_vosk(self, pcm: bytes) -> Transcription:
        self.load()
        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE)
        recognizer.SetWords(False)
        chunk = 4000
        for offset in range(0, len(pcm), chunk):
            if recognizer.AcceptWaveform(pcm[offset : offset + chunk]):
                pass
        final = json.loads(recognizer.FinalResult() or "{}")
        return Transcription((final.get("text") or "").strip(), "vosk")

    def _transcribe_google(self, pcm: bytes) -> Transcription:
        import speech_recognition as sr

        audio = sr.AudioData(pcm, SAMPLE_RATE, 2)
        recognizer = sr.Recognizer()
        text = recognizer.recognize_google(audio, language=self.language)
        return Transcription(text.strip(), "google")


def download_voice_model(model_dir: Path) -> Path | None:
    return ensure_model(model_dir, allow_download=True)