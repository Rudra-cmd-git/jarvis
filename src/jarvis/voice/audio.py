"""Microphone capture with a tiny energy-based VAD.

Uses sounddevice's raw callback so NumPy is not required. Audio is mono 16 kHz
16-bit PCM, exactly what Vosk expects.
"""
from __future__ import annotations

import array
import logging
import math
import threading
import time
from typing import Callable

logger = logging.getLogger("jarvis.voice.audio")

SAMPLE_RATE = 16000
FRAME_MS = 30
SILENCE_DBFS = -45.0


def input_devices() -> list[dict]:
    try:
        import sounddevice as sd

        devices = []
        for index, device in enumerate(sd.query_devices()):
            if device.get("max_input_channels", 0) > 0:
                devices.append({"index": index, "name": device["name"], "channels": device["max_input_channels"]})
        return devices
    except Exception as exc:  # pragma: no cover - depends on host audio
        logger.warning("Could not enumerate audio inputs: %s", exc)
        return []


def default_input_index() -> int | None:
    try:
        import sounddevice as sd

        index = sd.default.device[0]
        if index is not None and index >= 0:
            return int(index)
    except Exception:
        pass
    devices = input_devices()
    return devices[0]["index"] if devices else None


def _rms(data: bytes) -> float:
    if not data:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[: len(data) - (len(data) % 2)])
    if not samples:
        return 0.0
    total = 0.0
    for sample in samples:
        total += float(sample) * float(sample)
    return math.sqrt(total / len(samples))


def _dbfs(rms: float) -> float:
    if rms <= 0:
        return -100.0
    return 20.0 * math.log10(rms / 32768.0)


class MicRecorder:
    """Records until stopped, trimming leading/trailing silence."""

    def __init__(self, on_level: Callable[[float], None] | None = None) -> None:
        self.on_level = on_level
        self._frames: list[bytes] = []
        self._levels: list[float] = []
        self._lock = threading.Lock()

    def record_until(
        self,
        stop_event: threading.Event,
        *,
        max_seconds: float = 30.0,
        vad: bool = True,
        device: int | None = None,
    ) -> bytes:
        import sounddevice as sd

        self._frames = []
        self._levels = []
        blocksize = int(SAMPLE_RATE * FRAME_MS / 1000) * 2  # bytes
        started = time.monotonic()

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                logger.debug("Audio input status: %s", status)
            data = bytes(indata)
            level = _dbfs(_rms(data))
            self._frames.append(data)
            self._levels.append(level)
            if self.on_level:
                self.on_level(max(0.0, min(1.0, (level + 60.0) / 60.0)))

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=blocksize // 2,
                device=device,
                callback=callback,
            ):
                while not stop_event.is_set() and (time.monotonic() - started) < max_seconds:
                    time.sleep(FRAME_MS / 1000.0)
        except Exception as exc:
            logger.warning("Microphone capture failed: %s", exc)
            return b""

        if self.on_level:
            self.on_level(0.0)
        return self._trim(vad)

    def record_seconds(self, seconds: float, *, vad: bool = True) -> bytes:
        stop = threading.Event()
        timer = threading.Timer(max(0.2, seconds), stop.set)
        timer.start()
        try:
            return self.record_until(stop, max_seconds=seconds + 1.0, vad=vad)
        finally:
            timer.cancel()

    def _trim(self, vad: bool) -> bytes:
        if not self._frames:
            return b""
        data = b"".join(self._frames)
        if not vad:
            return data
        speech = [i for i, level in enumerate(self._levels) if level > SILENCE_DBFS]
        if not speech:
            return b""
        first, last = speech[0], speech[-1]
        padding = 3
        first = max(0, first - padding)
        last = min(len(self._frames) - 1, last + padding)
        return b"".join(self._frames[first : last + 1])