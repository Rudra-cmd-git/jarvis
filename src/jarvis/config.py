"""Application paths and user configuration.

Configuration lives in %APPDATA%\\JARVIS so it survives reinstalls and is never
stored inside the (possibly synced) source folder. Secrets are kept separately
and encrypted with Windows DPAPI - see jarvis.security.secrets.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_DIR_NAME = "JARVIS"
CONFIG_VERSION = 1


def _default_roots() -> list[str]:
    home = Path.home()
    candidates = [home, home / "Desktop", home / "Documents", home / "Downloads"]
    return [str(p) for p in candidates if p.exists()]


def _appdata_dirs() -> tuple[Path, Path]:
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        appdata = Path.home() / ".config"
        localappdata = Path.home() / ".local" / "share"
    return appdata / APP_DIR_NAME, localappdata / APP_DIR_NAME


@dataclass
class AppPaths:
    config_dir: Path
    data_dir: Path
    log_dir: Path
    models_dir: Path
    screenshot_dir: Path
    plugins_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def secrets_file(self) -> Path:
        return self.config_dir / "secrets.bin"

    @property
    def database_file(self) -> Path:
        return self.data_dir / "jarvis.db"

    def ensure(self) -> None:
        for directory in (
            self.config_dir,
            self.data_dir,
            self.log_dir,
            self.models_dir,
            self.screenshot_dir,
            self.plugins_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def get_paths() -> AppPaths:
    config_dir, data_dir = _appdata_dirs()
    paths = AppPaths(
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=config_dir / "logs",
        models_dir=data_dir / "models",
        screenshot_dir=data_dir / "screenshots",
        plugins_dir=data_dir / "plugins",
    )
    paths.ensure()
    return paths


@dataclass
class AppConfig:
    """User-editable settings. Secrets never live here."""

    # --- AI engine ---
    provider: str = "deepseek"
    model: str = ""
    base_url: str = ""
    temperature: float = 0.6
    max_tokens: int = 1200
    request_timeout: float = 90.0
    max_tool_iterations: int = 8
    agent_mode: bool = False
    history_limit: int = 20

    # --- Personality / language ---
    assistant_name: str = "JARVIS"
    personality: str = (
        "Calm, precise and quietly witty, like a highly capable butler. "
        "Be concise by default, explain only what matters, never flatter the user, "
        "and admit uncertainty instead of inventing facts."
    )
    language: str = "auto"  # auto | english | hinglish
    response_style: str = "concise"  # concise | detailed

    # --- Voice ---
    voice_enabled: bool = True
    tts_voice: str = ""
    tts_rate: int = 0
    tts_volume: float = 1.0
    stt_backend: str = "vosk"  # vosk | windows
    wake_word_enabled: bool = False
    wake_word: str = "jarvis"
    push_to_talk_enabled: bool = True

    # --- Safety ---
    memory_enabled: bool = True
    confirm_medium: bool = True
    allow_high_risk: bool = False
    allowed_roots: list[str] = field(default_factory=_default_roots)
    web_untrusted_wrap: bool = True

    # --- UI ---
    animations: bool = True
    low_spec: bool = False
    theme_intensity: float = 1.0
    start_minimized: bool = False
    confirm_on_exit: bool = False

    # --- Diagnostics ---
    log_level: str = "INFO"

    # ------------------------------------------------------------------ utils
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        cfg = cls()
        for key, value in (data or {}).items():
            if not hasattr(cfg, key):
                continue
            current = getattr(cfg, key)
            try:
                if isinstance(current, bool) and not isinstance(value, bool):
                    value = str(value).strip().lower() in {"1", "true", "yes", "on"}
                elif isinstance(current, list) and isinstance(value, str):
                    value = [v.strip() for v in value.split(";") if v.strip()]
                elif isinstance(current, float):
                    value = float(value)
                elif isinstance(current, int) and not isinstance(value, bool):
                    value = int(value)
                setattr(cfg, key, value)
            except (TypeError, ValueError):
                continue
        return cfg

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty means valid)."""
        problems: list[str] = []
        if self.provider not in {"deepseek", "openrouter", "custom"}:
            problems.append(f"Unknown provider '{self.provider}'.")
        if self.temperature < 0 or self.temperature > 2:
            problems.append("Temperature must be between 0 and 2.")
        if self.max_tokens < 64:
            problems.append("max_tokens should be at least 64.")
        if self.max_tool_iterations < 1 or self.max_tool_iterations > 25:
            problems.append("max_tool_iterations must be between 1 and 25.")
        if not self.allowed_roots:
            problems.append("At least one allowed folder is required for file tools.")
        return problems


def load_config(paths: AppPaths | None = None) -> AppConfig:
    paths = paths or get_paths()
    data: dict[str, Any] = {}
    if paths.config_file.exists():
        try:
            data = json.loads(paths.config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Corrupt config must never brick the app; fall back to defaults.
            data = {}
    cfg = AppConfig.from_dict(data)
    _apply_env(cfg)
    cfg.allowed_roots = _normalise_roots(cfg.allowed_roots)
    return cfg


def save_config(cfg: AppConfig, paths: AppPaths | None = None) -> None:
    paths = paths or get_paths()
    payload = cfg.to_dict()
    payload["version"] = CONFIG_VERSION
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="config-", suffix=".json", dir=str(paths.config_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(tmp_name, paths.config_file)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _normalise_roots(roots: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in roots:
        try:
            path = Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()
        except OSError:
            continue
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        result.append(str(path))
    return result or _default_roots()


def _apply_env(cfg: AppConfig) -> None:
    provider = os.environ.get("JARVIS_PROVIDER", "").strip()
    if provider:
        cfg.provider = provider
    model = os.environ.get("JARVIS_MODEL_NAME", "").strip()
    if model:
        cfg.model = model
    base_url = os.environ.get("JARVIS_BASE_URL", "").strip()
    if base_url:
        cfg.base_url = base_url
    log_level = os.environ.get("JARVIS_LOG_LEVEL", "").strip().upper()
    if log_level in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        cfg.log_level = log_level


def default_model_for(provider: str) -> str:
    return {
        "deepseek": "deepseek-chat",
        "openrouter": "openai/gpt-4o-mini",
        "custom": "",
    }.get(provider, "")