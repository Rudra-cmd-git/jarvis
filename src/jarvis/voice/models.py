"""Vosk model download and discovery (offline speech recognition)."""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger("jarvis.voice.models")

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def find_model(models_dir: Path) -> Path | None:
    preferred = models_dir / MODEL_NAME
    if (preferred / "am").exists():
        return preferred
    for candidate in sorted(models_dir.glob("vosk-model-*")):
        if (candidate / "am").exists():
            return candidate
    return None


def ensure_model(models_dir: Path, *, allow_download: bool = True) -> Path | None:
    """Return a usable model path, downloading the small English model once."""
    existing = find_model(models_dir)
    if existing is not None:
        return existing
    if not allow_download:
        return None
    models_dir.mkdir(parents=True, exist_ok=True)
    archive = models_dir / f"{MODEL_NAME}.zip"
    logger.info("Downloading Vosk model (%s)", MODEL_URL)
    try:
        with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=180.0) as response:
            response.raise_for_status()
            with archive.open("wb") as handle:
                for chunk in response.iter_bytes(262144):
                    handle.write(chunk)
    except Exception as exc:
        logger.warning("Vosk model download failed: %s", exc)
        archive.unlink(missing_ok=True)
        return None

    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(models_dir)
    except zipfile.BadZipFile as exc:
        logger.warning("Downloaded Vosk model archive is corrupt: %s", exc)
        return None
    finally:
        archive.unlink(missing_ok=True)

    model = find_model(models_dir)
    if model is None:
        logger.warning("Vosk model archive did not contain an expected folder")
    return model