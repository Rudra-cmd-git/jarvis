import pytest

from jarvis.ai.providers import PROVIDERS, get_preset, resolve_endpoint
from jarvis.config import AppConfig
from jarvis.core.errors import ConfigError
from jarvis.security.secrets import SecretStore


def test_deepseek_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key-123")
    cfg = AppConfig()
    cfg.provider = "deepseek"
    endpoint = resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))
    assert endpoint.base_url == "https://api.deepseek.com/v1"
    assert endpoint.model == "deepseek-chat"
    assert endpoint.api_key == "key-123"


def test_openrouter_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    cfg = AppConfig()
    cfg.provider = "openrouter"
    endpoint = resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))
    assert endpoint.base_url == "https://openrouter.ai/api/v1"
    assert endpoint.model == PROVIDERS["openrouter"].default_model
    assert endpoint.api_key == "or-key"


def test_custom_endpoint_requires_base_url_and_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_API_KEY", "local-key")
    cfg = AppConfig()
    cfg.provider = "custom"
    cfg.base_url = "http://127.0.0.1:11434/v1"
    cfg.model = "qwen2.5"
    endpoint = resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))
    assert endpoint.api_key == "local-key"
    assert endpoint.base_url.endswith("/v1")

    cfg.base_url = ""
    with pytest.raises(ConfigError):
        resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))

    cfg.base_url = "http://127.0.0.1:11434/v1"
    cfg.model = ""
    with pytest.raises(ConfigError):
        resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))


def test_missing_deepseek_key_is_explained(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cfg = AppConfig()
    cfg.provider = "deepseek"
    with pytest.raises(ConfigError) as excinfo:
        resolve_endpoint(cfg, SecretStore(tmp_path / "secrets.bin"))
    assert "DEEPSEEK_API_KEY" in str(excinfo.value)


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ConfigError):
        get_preset("moonbeam")