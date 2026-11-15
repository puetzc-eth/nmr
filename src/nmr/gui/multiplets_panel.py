"""Side panel listing the multiplets of the current spectrum and the report text."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nmr.core.multiplets import Multiplet

PATTERN_COLUMN = 1
NUCLEI_COLUMN = 3


class MultipletsPanel(QWidget):
    pattern_changed = Signal(int, object)
    """Row and the pattern the user typed; None asks for the automatic one again."""
    nuclei_changed = Signal(int, object)
    """Row and the number of nuclei the user typed; None for the automatic one."""
    delete_requested = Signal(int)
    clear_requested = Signal()
    copy_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._multiplets: list[Multiplet] = []
        self._report = ""
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["δ (ppm)", "Type", "J (Hz)", "Nuclei"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        for column in (0, 1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setToolTip(
            "Double-click Type or Nuclei to correct a value.\n"
            "Clear the cell to get the automatic value back."
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("The multiplet report appears here.")
        self.report.setFixedHeight(84)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.clear_button = QPushButton("Delete all")
        self.clear_button.clicked.connect(self.clear_requested)
        self.copy_button = QPushButton("Copy report")
        self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self.copy_requested)
        delete_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_key.activated.connect(self._delete_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        buttons.addWidget(self.copy_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.addWidget(self.table)
        layout.addWidget(self.report)
        layout.addLayout(buttons)
        self._update_buttons()

    def set_multiplets(self, multiplets: list[Multiplet], report: str) -> None:
        self._multiplets, self._report = multiplets, report
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(multiplets))
        read_only = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for row, multiplet in enumerate(multiplets):
            if multiplet.pattern == "m":
                shift = f"{multiplet.high_ppm:.2f} – {multiplet.low_ppm:.2f}"
            else:
                shift = f"{multiplet.shift_ppm:.3f}"
            cells = (
                shift,
                multiplet.pattern,
                ", ".join(f"{j:.1f}" for j in multiplet.couplings_hz),
                str(multiplet.nuclei),
            )
            for column, text in enumerate(cells):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    editable = column in (PATTERN_COLUMN, NUCLEI_COLUMN)
                    item.setFlags(read_only | Qt.ItemFlag.ItemIsEditable if editable else read_only)
                    self.table.setItem(row, column, item)
                if item.text() != text:
                    item.setText(text)
        if 0 <= selected < len(multiplets):
            self.table.selectRow(selected)
        self.table.blockSignals(False)
        if self.report.toPlainText() != report:
            self.report.setPlainText(report)
        self._update_buttons()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        text = item.text().strip()
        if item.column() == PATTERN_COLUMN:
            self.pattern_changed.emit(item.row(), text or None)
        elif item.column() == NUCLEI_COLUMN:
            if not text:
                self.nuclei_changed.emit(item.row(), None)
            elif text.isdigit() and int(text) > 0:
                self.nuclei_changed.emit(item.row(), int(text))
            else:
                # Not a usable number: put the old text back.
                self.set_multiplets(self._multiplets, self._report)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0 and self.table.selectedItems():
            self.delete_requested.emit(row)

    def _update_buttons(self) -> None:
        has_rows = self.table.rowCount() > 0
        self.delete_button.setEnabled(bool(self.table.selectedItems()))
        self.clear_button.setEnabled(has_rows)
        self.copy_button.setEnabled(has_rows)
