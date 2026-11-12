"""Visual identity: colours, fonts and the Qt stylesheet.

The palette is original: deep navy-black, cyan accents, amber for warnings and
red for destructive actions. Glow is drawn by the orb widget, not by expensive
desktop effects, so it stays light on low-end machines.
"""
from __future__ import annotations

BG = "#04070d"
BG_ELEVATED = "#070c15"
PANEL = "#0a111c"
PANEL_ALT = "#0d1624"
BORDER = "#172436"
CYAN = "#3fe0ff"
CYAN_SOFT = "#1d7f96"
CYAN_DARK = "#0d3a47"
TEXT = "#dce8f5"
MUTED = "#7d8ea6"
DANGER = "#ff4d61"
WARN = "#ffb648"
OK = "#43e0a0"
FONT = "Segoe UI"
MONO = "Cascadia Mono, Consolas, monospace"


def stylesheet(intensity: float = 1.0, low_spec: bool = False) -> str:
    glow = "0px 0px 10px rgba(63,224,255,0.25);" if not low_spec else ""
    radius = 10
    return f"""
    * {{
        font-family: "{FONT}";
        font-size: 13px;
        color: {TEXT};
    }}
    QMainWindow, QWidget#Root, QDialog {{
        background-color: {BG};
    }}
    QLabel#Brand {{
        font-size: 16px;
        font-weight: 600;
        letter-spacing: 3px;
        color: {CYAN};
    }}
    QLabel#Muted {{ color: {MUTED}; }}
    QLabel#H1 {{ font-size: 20px; font-weight: 600; }}
    QLabel#H2 {{ font-size: 15px; font-weight: 600; color: {CYAN}; }}
    QFrame#Card {{
        background-color: {PANEL};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
    }}
    QFrame#CardAlt {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
    }}
    QFrame#Divider {{ background-color: {BORDER}; max-height: 1px; border: none; }}
    QPushButton {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 14px;
        color: {TEXT};
    }}
    QPushButton:hover {{ border-color: {CYAN_SOFT}; }}
    QPushButton:pressed {{ background-color: {CYAN_DARK}; }}
    QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}
    QPushButton#Primary {{
        background-color: {CYAN_DARK};
        border: 1px solid {CYAN_SOFT};
        color: {CYAN};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background-color: #114b5a; }}
    QPushButton#Danger {{
        background-color: #2a0d13;
        border: 1px solid #6d2230;
        color: {DANGER};
        font-weight: 600;
    }}
    QPushButton#Danger:hover {{ background-color: #3a1119; border-color: {DANGER}; }}
    QPushButton#Ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {MUTED};
    }}
    QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {BORDER}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 10px;
        selection-background-color: {CYAN_DARK};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {CYAN_SOFT};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        selection-background-color: {CYAN_DARK};
    }}
    QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        padding: 8px 16px;
        color: {MUTED};
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {CYAN}; border-bottom: 2px solid {CYAN}; }}
    QTableWidget, QListWidget, QTreeWidget {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER};
    }}
    QTableWidget::item, QListWidget::item {{ padding: 6px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background-color: {CYAN_DARK}; color: {TEXT};
    }}
    QHeaderView::section {{
        background-color: {PANEL_ALT};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px;
        color: {MUTED};
    }}
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {CYAN_SOFT}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; }}
    QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border: 1px solid {BORDER};
        border-radius: 4px; background: {BG_ELEVATED};
    }}
    QCheckBox::indicator:checked {{ background: {CYAN_DARK}; border-color: {CYAN}; }}
    QSlider::groove:horizontal {{
        height: 4px; background: {BORDER}; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
        background: {CYAN}; border: 2px solid {BG};
    }}
    QProgressBar {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER};
        border-radius: 6px;
        text-align: center;
        color: {MUTED};
    }}
    QProgressBar::chunk {{
        background-color: {CYAN_SOFT};
        border-radius: 5px;
    }}
    QToolTip {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        color: {TEXT};
        padding: 5px;
    }}
    QMenuBar {{ background: {BG}; }}
    QMenu {{ background-color: {PANEL_ALT}; border: 1px solid {BORDER}; }}
    QMenu::item:selected {{ background-color: {CYAN_DARK}; }}
    """