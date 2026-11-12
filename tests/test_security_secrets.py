from pathlib import Path

import pytest

from jarvis.security.secrets import SecretStore


def test_secret_store_roundtrip(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.bin")
    if not store.available():
        pytest.skip("Windows DPAPI is not available in this environment")
    assert store.set("provider_api_key:test", "super-secret-value") is True
    assert store.get("provider_api_key:test") == "super-secret-value"
    store.delete("provider_api_key:test")
    assert store.get("provider_api_key:test") is None


def test_secret_store_does_not_write_plaintext(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.bin")
    if not store.available():
        pytest.skip("Windows DPAPI is not available in this environment")
    store.set("provider_api_key:test", "plain-text-marker")
    raw = (tmp_path / "secrets.bin").read_bytes()
    assert b"plain-text-marker" not in raw