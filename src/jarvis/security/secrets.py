"""Encrypted secret storage for API keys.

Keys are stored in %APPDATA%\\JARVIS\\secrets.bin as a base64-wrapped DPAPI blob.
Environment variables (.env) are always supported as a fallback and take
precedence, which makes the app usable on machines where DPAPI is unavailable.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from pathlib import Path

from jarvis.security import dpapi

logger = logging.getLogger("jarvis.security.secrets")

ENV_PREFIX = "JARVIS_"
PROVIDER_ENV_KEYS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "custom": "JARVIS_API_KEY",
}


class SecretStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._cache: dict[str, str] | None = None

    # ------------------------------------------------------------------ public
    def available(self) -> bool:
        return dpapi.available()

    def set(self, key: str, value: str) -> bool:
        if not value:
            self.delete(key)
            return True
        if not self.available():
            logger.error("DPAPI unavailable; refusing to store secret '%s' in plaintext", key)
            return False
        data = self._load()
        data[key] = base64.b64encode(dpapi.protect(value)).decode("ascii")
        return self._save(data)

    def get(self, key: str) -> str | None:
        env_value = os.environ.get(f"{ENV_PREFIX}{key.upper()}")
        if env_value:
            return env_value
        data = self._load()
        blob = data.get(key)
        if not blob:
            return None
        try:
            return dpapi.unprotect(base64.b64decode(blob.encode("ascii")))
        except Exception as exc:  # pragma: no cover - corrupt store
            logger.warning("Could not decrypt secret '%s': %s", key, exc)
            return None

    def delete(self, key: str) -> None:
        data = self._load()
        if key in data:
            data.pop(key)
            self._save(data)

    def key_for_provider(self, provider: str) -> str:
        return f"provider_api_key:{provider}"

    def provider_key(self, provider: str) -> str | None:
        env_name = PROVIDER_ENV_KEYS.get(provider)
        if env_name:
            value = os.environ.get(env_name)
            if value:
                return value
        return self.get(self.key_for_provider(provider))

    def store_provider_key(self, provider: str, value: str) -> bool:
        return self.set(self.key_for_provider(provider), value)

    # ----------------------------------------------------------------- private
    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._cache = raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            logger.warning("Secret store unreadable; starting empty")
            self._cache = {}
        return self._cache

    def _save(self, data: dict[str, str]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="secrets-", suffix=".bin", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._cache = data
            return True
        except OSError as exc:
            logger.error("Failed to persist secret store: %s", exc)
            return False