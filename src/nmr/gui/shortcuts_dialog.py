"""The keyboard and mouse reference shown under Help > Keyboard Shortcuts."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nmr.gui import theme

SHORTCUTS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "View",
        [
            ("Z", "Zoom tool; press again to switch horizontal / vertical / box"),
            ("Shift+Z", "Zoom out"),
            ("F", "Full spectrum"),
            ("H", "Fit to highest intensity"),
            ("P", "Pan tool; press again to switch free / horizontal / vertical"),
            ("C", "Crosshair cursor; drag to measure a distance in ppm and Hz"),
            ("Esc", "Back to the select tool"),
            ("Mouse wheel", "Increase / decrease intensity"),
            ("+ / −", "Increase / decrease intensity"),
            ("Ctrl+Mouse wheel", "Zoom horizontally around the cursor"),
            ("Drag (select tool)", "Move the spectrum"),
            ("Ctrl+F", "Show the FID instead of the spectrum"),
        ],
    ),
    (
        "Processing",
        [
            ("Shift+P", "Manual phase correction"),
            ("   Drag up / down", "Zero-order phase (PH0)"),
            ("   Right-drag or Ctrl+drag", "First-order phase (PH1)"),
            ("   Shift+drag", "Fine steps"),
            ("   Click", "Set the pivot"),
            ("Ctrl+Shift+P", "Automatic phase correction"),
            ("L", "Reference: click a signal and enter its chemical shift"),
        ],
    ),
    (
        "Analysis",
        [
            ("I", "Integration: drag across a signal"),
            ("Delete", "Remove the integral selected in the table"),
        ],
    ),
    (
        "File and edit",
        [
            ("Ctrl+N", "New, empty project"),
            ("Ctrl+O", "Open a project, or import data files and ZIP archives"),
            ("Ctrl+Shift+O", "Import a data folder"),
            ("Ctrl+S", "Save the project"),
            ("Ctrl+Shift+S", "Save the project under a new name"),
            ("PgUp / PgDown", "Previous / next spectrum"),
            ("Delete", "Remove the spectrum selected in the list"),
            ("Ctrl+Z", "Undo"),
            ("Ctrl+Y / Ctrl+Shift+Z", "Redo"),
            ("Ctrl+C", "Copy the spectrum as an image"),
            ("F1", "This list"),
            ("Ctrl+Q", "Quit"),
        ],
    ),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(560, 620)

        rows = sum(len(entries) + 1 for _, entries in SHORTCUTS)
        table = QTableWidget(rows, 2)
        table.setHorizontalHeaderLabels(["Shortcut", "Action"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

        bold = QFont(self.font())
        bold.setBold(True)
        row = 0
        for section, entries in SHORTCUTS:
            heading = QTableWidgetItem(section)
            heading.setFont(bold)
            heading.setForeground(QColor(theme.ACCENT))
            table.setItem(row, 0, heading)
            table.setSpan(row, 0, 1, 2)
            row += 1
            for keys, action in entries:
                table.setItem(row, 0, QTableWidgetItem(keys))
                table.setItem(row, 1, QTableWidgetItem(action))
                row += 1
        self.table = table

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(table)
        layout.addWidget(buttons)
