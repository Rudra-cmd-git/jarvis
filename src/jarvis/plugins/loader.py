"""Load optional third-party tools from the user's plugin folder.

A plugin is a Python module that defines ``register(registry, config)``. Plugins
run with the same permissions as JARVIS, so only install code you trust.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from jarvis.config import AppConfig
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.plugins")


def load_plugins(registry: ToolRegistry, plugins_dir: Path, cfg: AppConfig) -> list[str]:
    loaded: list[str] = []
    if not plugins_dir.exists():
        return loaded
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if callable(register):
                register(registry, cfg)
                loaded.append(path.name)
                logger.info("Loaded plugin %s", path.name)
            else:
                logger.warning("Plugin %s has no register(registry, config) function", path.name)
        except Exception:  # noqa: BLE001 - a bad plugin must not stop the app
            logger.exception("Failed to load plugin %s", path.name)
    return loaded