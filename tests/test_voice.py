import pytest

from jarvis.config import get_paths
from jarvis.voice.models import find_model
from jarvis.voice.stt import SpeechToText


def test_vosk_backend_reports_model_state() -> None:
    paths = get_paths()
    stt = SpeechToText(backend="vosk", model_dir=paths.models_dir)
    available, detail = stt.available()
    if find_model(paths.models_dir) is None:
        assert available is False
        assert "model" in detail.lower()
    else:
        assert available is True
        assert "vosk-model" in detail


def test_unknown_backend_is_reported() -> None:
    stt = SpeechToText(backend="carrier-pigeon")
    available, detail = stt.available()
    assert available is False
    assert "unknown" in detail.lower()