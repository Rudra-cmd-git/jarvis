import time
from pathlib import Path

from jarvis.config import AppConfig, AppPaths
from jarvis.core.events import RecordingSink
from jarvis.ui.controller import AppController


def _paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir = tmp_path / "logs",
        models_dir = tmp_path / "models",
        screenshot_dir = tmp_path / "shots",
        plugins_dir = tmp_path / "plugins",
    )
    paths.ensure()
    return paths


def _wait_for_assistant(ui: RecordingSink, timeout: float = 8.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event, payload in ui.events:
            if event == "message" and payload.get("role") == "assistant":
                return payload.get("content", "")
        time.sleep(0.05)
    return None


def test_controller_runs_saved_workflow(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    ui = RecordingSink()
    controller = AppController(paths=paths, bridge=ui)
    controller.cfg.voice_enabled = False
    controller.store.save_workflow(
        "T", "test", [{"tool": "add_todo", "args": {"text": "from controller"}}]
    )
    controller.start()
    try:
        controller.run_workflow("T")
        content = _wait_for_assistant(ui)
        assert content is not None
        assert "1/1" in content
        assert controller.store.list_todos()[0]["text"] == "from controller"
        assert any(event == "task" for event, _ in ui.events)
    finally:
        controller.shutdown()


def test_controller_reports_missing_workflow(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    ui = RecordingSink()
    controller = AppController(paths=paths, bridge=ui)
    controller.start()
    try:
        controller.run_workflow("does-not-exist")
        time.sleep(0.3)
        notifications = [payload for event, payload in ui.events if event == "notify"]
        assert notifications
        assert "not found" in notifications[-1][0].lower() or "not found" in notifications[-1][1].lower()
    finally:
        controller.shutdown()