from pathlib import Path

import pytest

from jarvis.config import AppConfig, AppPaths, load_config, save_config
from jarvis.core.util import contains_secret, redact, truncate


def test_defaults_and_roundtrip(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "c", tmp_path / "d", tmp_path / "l", tmp_path / "m", tmp_path / "s", tmp_path / "p")
    cfg = AppConfig()
    cfg.assistant_name = "Jarvis"
    cfg.temperature = 0.25
    save_config(cfg, paths)
    loaded = load_config(paths)
    assert loaded.assistant_name == "Jarvis"
    assert loaded.temperature == 0.25
    assert loaded.provider == "deepseek"


def test_validation_reports_bad_values() -> None:
    cfg = AppConfig()
    cfg.temperature = 5
    cfg.max_tokens = 1
    cfg.provider = "moonbeam"
    problems = cfg.validate()
    assert any("temperature" in p.lower() for p in problems)
    assert any("provider" in p.lower() for p in problems)


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_PROVIDER", "openrouter")
    monkeypatch.setenv("JARVIS_MODEL_NAME", "custom/model")
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "DEBUG")
    paths = AppPaths(Path("c"), Path("d"), Path("l"), Path("m"), Path("s"), Path("p"))
    cfg = load_config(paths)
    assert cfg.provider == "openrouter"
    assert cfg.model == "custom/model"
    assert cfg.log_level == "DEBUG"


def test_redaction() -> None:
    text = "My api key is sk-ABCDEFGHIJKLMNOP1234 and password=hunter2"
    cleaned = redact(text)
    assert "sk-ABCDEFGHIJKLMNOP1234" not in cleaned
    assert contains_secret("token: abcdefghijklmnopqrstuvwxyz123456")


def test_truncate() -> None:
    assert truncate("hello", 3) == "he…"