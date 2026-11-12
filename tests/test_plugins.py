from pathlib import Path

from jarvis.config import AppConfig
from jarvis.plugins.loader import load_plugins
from jarvis.tools.registry import ToolRegistry


def test_plugin_is_loaded_and_registered(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    plugin = plugins / "demo_plugin.py"
    plugin.write_text(
        "from jarvis.tools.registry import ToolSpec\n"
        "def register(registry, config):\n"
        "    registry.register(ToolSpec(name='plugin_ping', description='ping', "
        "handler=lambda ctx: 'pong', risk=__import__('jarvis.security.permissions', fromlist=['Risk']).Risk.LOW))\n",
        encoding="utf-8",
    )
    registry = ToolRegistry()
    loaded = load_plugins(registry, plugins, AppConfig())
    assert "demo_plugin.py" in loaded
    assert "plugin_ping" in registry.names()


def test_broken_plugin_does_not_break_loading(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "broken.py").write_text("raise RuntimeError('bad plugin')\n", encoding="utf-8")
    (plugins / "good.py").write_text(
        "def register(registry, config):\n"
        "    from jarvis.tools.registry import ToolSpec\n"
        "    registry.register(ToolSpec(name='good_tool', description='ok', handler=lambda ctx: 'ok'))\n",
        encoding="utf-8",
    )
    registry = ToolRegistry()
    loaded = load_plugins(registry, plugins, AppConfig())
    assert loaded == ["good.py"]
    assert "good_tool" in registry.names()