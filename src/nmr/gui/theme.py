"""Application-wide look: one light theme that is identical on all platforms."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#2563eb"
SPECTRUM = "#1e3a8a"
PIVOT = "#ea580c"
CROSSHAIR = "#64748b"
AXIS = "#475569"
TEXT = "#0f172a"
MUTED = "#64748b"
SURFACE = "#f8fafc"
BORDER = "#e2e8f0"

STYLESHEET = f"""
QMainWindow, QDialog {{ background: {SURFACE}; }}
QMenuBar {{ background: white; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 5px; background: transparent; }}
QMenuBar::item:selected {{ background: #eff6ff; color: {ACCENT}; }}
QMenu {{ background: white; border: 1px solid {BORDER}; padding: 5px; }}
QMenu::item {{ padding: 6px 28px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #eff6ff; color: {TEXT}; }}
QMenu::item:disabled {{ color: #94a3b8; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QToolBar {{ background: white; border: none; border-bottom: 1px solid {BORDER};
            padding: 6px 8px; spacing: 3px; }}
QToolBar::separator {{ width: 1px; background: {BORDER}; margin: 5px 7px; }}
QToolButton {{ padding: 6px 11px; border: 1px solid transparent; border-radius: 7px;
               color: {TEXT}; }}
QToolButton:hover {{ background: #f1f5f9; }}
QToolButton:pressed {{ background: {BORDER}; }}
QToolButton:checked {{ background: #eff6ff; border-color: #bfdbfe; color: {ACCENT}; }}
QToolButton:disabled {{ color: #94a3b8; }}

QDockWidget {{ color: {MUTED}; font-weight: 600; }}
QDockWidget::title {{ background: {SURFACE}; padding: 10px 12px 4px 12px; }}
QGroupBox {{ background: white; border: 1px solid {BORDER}; border-radius: 9px;
             margin-top: 22px; padding: 10px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 4px; top: 2px; color: {MUTED}; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}

QDoubleSpinBox, QSpinBox, QComboBox {{ background: white; border: 1px solid #cbd5e1;
    border-radius: 6px; padding: 4px 6px; min-height: 20px; font-weight: normal; }}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {{ background: #f1f5f9;
    color: #94a3b8; }}
QPushButton {{ background: white; border: 1px solid #cbd5e1; border-radius: 7px;
               padding: 6px 14px; font-weight: normal; }}
QPushButton:hover {{ background: #f1f5f9; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:default {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton:disabled {{ color: #94a3b8; }}

QStatusBar {{ background: white; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 2px 8px; }}

QLabel#emptyHint {{ color: {MUTED}; font-size: 15px; }}
QTableWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 8px;
                gridline-color: transparent; }}
QTableWidget::item {{ padding: 4px 8px; }}
QHeaderView::section {{ background: {SURFACE}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 6px 8px; color: {MUTED}; font-weight: 600; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, colour in (
        (QPalette.ColorRole.Window, SURFACE),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, SURFACE),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.ToolTipBase, "#ffffff"),
        (QPalette.ColorRole.ToolTipText, TEXT),
        (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
