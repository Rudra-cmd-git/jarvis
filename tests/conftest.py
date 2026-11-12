"""Shared test fixtures."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.config import AppConfig, AppPaths
from jarvis.core.events import RecordingSink
from jarvis.memory.store import Store
from jarvis.security.permissions import PermissionPolicy
from jarvis.security.secrets import SecretStore
from jarvis.tools.context import ToolContext


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        models_dir = tmp_path / "models",
        screenshot_dir = tmp_path / "shots",
        plugins_dir = tmp_path / "plugins",
    )
    paths.ensure()
    return paths


@pytest.fixture
def cfg(paths: Path, tmp_path: Path) -> AppConfig:
    config = AppConfig()
    config.allowed_roots = [str(tmp_path / "workspace")]
    (tmp_path / "workspace").mkdir(exist_ok=True)
    config.confirm_medium = False
    config.memory_enabled = True
    config.voice_enabled = False
    return config


@pytest.fixture
def store(paths: AppPaths) -> Store:
    database = Store(paths.database_file)
    yield database
    database.close()


@pytest.fixture
def ui() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def ctx(cfg: AppConfig, paths: AppPaths, store: Store, ui: RecordingSink) -> ToolContext:
    from jarvis.security.permissions import ConfirmationResult

    async def allow(_request):
        return ConfirmationResult.ALLOW

    policy = PermissionPolicy(cfg, confirmer=allow)
    return ToolContext(
        config=cfg,
        paths=paths,
        store=store,
        secrets=SecretStore(paths.secrets_file),
        policy=policy,
        ui=ui,
    )


def run(coro):
    return asyncio.run(coro)