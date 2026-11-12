"""Provider presets and endpoint resolution.

All providers speak the OpenAI Chat Completions protocol, so one client covers
DeepSeek, OpenRouter and any compatible local server (Ollama, LM Studio, vLLM).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from jarvis.config import AppConfig, default_model_for
from jarvis.core.errors import ConfigError


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    base_url: str
    default_model: str
    key_env: str
    key_url: str
    notes: str


PROVIDERS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        key_env="DEEPSEEK_API_KEY",
        key_url="https://platform.deepseek.com/api-keys",
        notes="Low-cost, strong reasoning and tool calling. Uses the OpenAI-compatible API.",
    ),
    "openrouter": ProviderPreset(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="meta-llama/llama-3.3-70b-instruct:free",
        key_env="OPENROUTER_API_KEY",
        key_url="https://openrouter.ai/keys",
        notes="One key for many models, including free variants. Model names include the vendor prefix.",
    ),
    "custom": ProviderPreset(
        id="custom",
        label="Custom (OpenAI-compatible)",
        base_url="",
        default_model="",
        key_env="JARVIS_API_KEY",
        key_url="",
        notes="Point at Ollama (http://127.0.0.1:11434/v1), LM Studio, vLLM, Azure OpenAI or a proxy.",
    ),
}


def get_preset(provider: str) -> ProviderPreset:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise ConfigError(
            f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}"
        ) from exc


@dataclass
class ResolvedEndpoint:
    provider: str
    base_url: str
    api_key: str
    model: str


def resolve_endpoint(cfg: AppConfig, secrets) -> ResolvedEndpoint:
    """Return base URL, key and model, preferring env vars over stored secrets."""
    preset = get_preset(cfg.provider)
    api_key = secrets.provider_key(cfg.provider) if secrets is not None else None
    if not api_key:
        env_value = os.environ.get(preset.key_env, "").strip()
        api_key = env_value or None

    base_url = (cfg.base_url or preset.base_url).strip()
    if cfg.provider == "custom" and not base_url:
        base_url = os.environ.get("JARVIS_BASE_URL", "").strip()
    if not base_url:
        raise ConfigError(
            f"No API base URL configured for '{preset.label}'. "
            "Enter it in Settings > API or set JARVIS_BASE_URL."
        )

    model = (cfg.model or default_model_for(cfg.provider) or preset.default_model).strip()
    if not model:
        raise ConfigError(
            f"No model selected for '{preset.label}'. Choose one in Settings > API."
        )

    if cfg.provider != "custom" and not api_key:
        raise ConfigError(
            f"Missing API key for {preset.label}.\n"
            f"Add it in Settings > API, or set {preset.key_env} in .env.\n"
            f"Create a key at {preset.key_url}"
        )

    return ResolvedEndpoint(
        provider=cfg.provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key or "not-needed",
        model=model,
    )


def is_configured(cfg: AppConfig, secrets) -> tuple[bool, str]:
    try:
        endpoint = resolve_endpoint(cfg, secrets)
    except ConfigError as exc:
        return False, str(exc)
    return True, f"{endpoint.provider} / {endpoint.model}"