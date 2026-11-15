"""Application-wide look: one light theme that is identical on all platforms."""

import atexit
import shutil
import tempfile
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
ACCENT_SOFT = "#eff6ff"
ACCENT_LINE = "#bfdbfe"
SPECTRUM = "#1e3a8a"
PIVOT = "#ea580c"
INTEGRAL = "#059669"
CROSSHAIR = "#64748b"
AXIS = "#475569"
TEXT = "#0f172a"
MUTED = "#64748b"
FAINT = "#94a3b8"
SURFACE = "#f6f8fb"
BORDER = "#e2e8f0"
INPUT_BORDER = "#cbd5e1"

STYLESHEET = """
QMainWindow, QDialog {{ background: {SURFACE}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 5px 8px;
            border-radius: 5px; }}
QMenu {{ background: white; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 6px 28px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

/* ---- ribbon ---- */
QWidget#ribbon {{ background: white; border-bottom: 1px solid {BORDER}; }}
QTabBar#ribbonTabs {{ background: transparent; }}
QTabBar#ribbonTabs::tab {{ background: transparent; color: {MUTED}; border: none;
    border-bottom: 2px solid transparent; padding: 7px 14px 6px 14px; margin: 0 1px;
    font-weight: 600; }}
QTabBar#ribbonTabs::tab:hover {{ color: {TEXT}; }}
QTabBar#ribbonTabs::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QToolButton#ribbonButton {{ color: {TEXT}; border: 1px solid transparent; border-radius: 8px;
    padding: 5px 6px 3px 6px; font-size: 11px; }}
QToolButton#ribbonButton:hover {{ background: #f1f5f9; }}
QToolButton#ribbonButton:pressed {{ background: {BORDER}; }}
QToolButton#ribbonButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT_LINE};
    color: {ACCENT_DARK}; }}
QToolButton#ribbonButton:disabled {{ color: {FAINT}; }}
QFrame#ribbonSeparator {{ background: {BORDER}; margin: 8px 7px; }}

/* ---- side panels ---- */
QDockWidget {{ color: {MUTED}; font-weight: 600; font-size: 11px; }}
QDockWidget::title {{ background: {SURFACE}; padding: 12px 14px 6px 14px; }}
QMainWindow::separator {{ background: {SURFACE}; width: 5px; height: 5px; }}
QMainWindow::separator:hover {{ background: {ACCENT_LINE}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {SURFACE}; }}
QGroupBox {{ background: white; border: 1px solid {BORDER}; border-radius: 10px;
             margin-top: 24px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 4px; top: 4px; color: {MUTED}; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; color: {TEXT}; }}

QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{ background: white;
    border: 1px solid {INPUT_BORDER}; border-radius: 7px; padding: 5px 8px; min-height: 20px;
    font-weight: normal; selection-background-color: {ACCENT}; }}
QDoubleSpinBox:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {FAINT}; }}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border: 1px solid {ACCENT}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {{ background: #f1f5f9;
    color: {FAINT}; border-color: {BORDER}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({ASSETS}/chevron-down.png); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px; selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT}; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {INPUT_BORDER};
    border-radius: 5px; background: white; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT};
    image: url({ASSETS}/check.png); }}

QPushButton {{ background: white; border: 1px solid {INPUT_BORDER}; border-radius: 7px;
               padding: 6px 14px; font-weight: normal; color: {TEXT}; }}
QPushButton:hover {{ background: #f1f5f9; border-color: {FAINT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:default {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton:default:hover {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {BORDER}; }}

/* ---- lists and tables ---- */
QListWidget {{ background: {SURFACE}; border: none; outline: none; }}
QListWidget::item {{ background: white; border: 1px solid {BORDER}; border-radius: 10px;
                     padding: 6px; color: {TEXT}; }}
QListWidget::item:hover {{ border-color: {INPUT_BORDER}; }}
QListWidget::item:selected {{ border: 2px solid {ACCENT}; background: white; color: {TEXT}; }}
QTableWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 10px;
                gridline-color: transparent; outline: none; }}
QTableWidget::item {{ padding: 4px 8px; border: none; }}
QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid {BORDER};
    padding: 7px 8px; color: {MUTED}; font-weight: 600; font-size: 11px; }}
QTableCornerButton::section {{ background: white; border: none; }}

/* ---- scroll bars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {INPUT_BORDER}; border-radius: 3px; min-height: 28px;
                      min-width: 28px; }}
QScrollBar::handle:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- status bar ---- */
QStatusBar {{ background: white; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 3px 10px; }}

QLabel#emptyHint {{ color: {FAINT}; font-size: 15px; }}
"""

_assets: Path | None = None


def _asset_folder() -> Path:
    """Small images the style sheet refers to, rendered once per run from the icon set."""
    global _assets
    if _assets is None:
        from nmr.gui import icons

        _assets = Path(tempfile.mkdtemp(prefix="nmr-theme-"))
        atexit.register(shutil.rmtree, _assets, ignore_errors=True)
        icons.pixmap("chevron-down", 28, MUTED).save(str(_assets / "chevron-down.png"))
        icons.pixmap("check", 32).save(str(_assets / "check.png"))
    return _assets


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont(app.font())
    if font.pointSizeF() < 9.5:
        font.setPointSizeF(9.5)
    app.setFont(font)

    palette = QPalette()
    for role, colour in (
        (QPalette.ColorRole.Window, SURFACE),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, SURFACE),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.ToolTipBase, TEXT),
        (QPalette.ColorRole.ToolTipText, "#ffffff"),
        (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)

    colours = {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, str) and value.startswith("#")
    }
    app.setStyleSheet(STYLESHEET.format(ASSETS=_asset_folder().as_posix(), **colours))
