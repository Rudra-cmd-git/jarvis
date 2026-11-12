"""Application entry point."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from jarvis.config import get_paths, load_config
from jarvis.core.logging_setup import setup_logging


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dependency is required
        load_dotenv = None  # type: ignore

    if load_dotenv is not None:
        load_dotenv(_project_root() / ".env")
        load_dotenv(Path.cwd() / ".env")

    paths = get_paths()
    cfg = load_config(paths)
    setup_logging(cfg.log_level, paths.log_dir)
    logger = logging.getLogger("jarvis.app")

    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is not installed. Run scripts\\setup.ps1 (or pip install -r requirements.txt) first.",
            file=sys.stderr,
        )
        return 2

    from jarvis.ui.bridge import UiBridge
    from jarvis.ui.controller import AppController
    from jarvis.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setOrganizationName("JARVIS")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    bridge = UiBridge()
    controller = AppController(paths, bridge)
    window = MainWindow(controller)
    window.show()

    try:
        controller.start()
    except Exception as exc:  # noqa: BLE001 - show a usable error, then continue
        logger.exception("Backend startup failed")
        window._on_error(f"Startup failed: {exc}")

    if cfg.start_minimized:
        window.hide()

    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())