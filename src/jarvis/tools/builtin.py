"""Assemble the built-in tool registry."""
from __future__ import annotations

from jarvis.tools import apps, clipboard, files, memory_tools, productivity, screen, system, web, workflows
from jarvis.tools.registry import ToolRegistry

_MODULES = (apps, clipboard, files, memory_tools, productivity, screen, system, web, workflows)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in _MODULES:
        registry.register_all(module.build_specs())
    return registry