"""Side panel listing the integrals of the current spectrum."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nmr.core.integration import Integral

VALUE_COLUMN = 2


class IntegralsPanel(QWidget):
    reference_changed = Signal(int, float)
    """The user typed a new value for the integral in this row."""
    delete_requested = Signal(int)
    clear_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._integrals: list[Integral] = []
        self._ref_index = 0
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Range (ppm)", "Absolute", "Integral"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setToolTip(
            "Double-click a value in the Integral column to set it;\n"
            "all other integrals are scaled accordingly."
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.clear_button = QPushButton("Delete all")
        self.clear_button.clicked.connect(self.clear_requested)
        delete_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_key.activated.connect(self._delete_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self._update_buttons()

    def set_integrals(self, integrals: list[Integral], ref_index: int) -> None:
        """Show `integrals`; the reference integral is printed in bold."""
        self._integrals, self._ref_index = integrals, ref_index
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(integrals))
        bold = QFont(self.font())
        bold.setBold(True)
        read_only = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for row, integral in enumerate(integrals):
            cells = (
                f"{integral.high_ppm:.3f} – {integral.low_ppm:.3f}",
                f"{integral.area:.4g}",
                f"{integral.value:.2f}",
            )
            for column, text in enumerate(cells):
                existing = self.table.item(row, column)
                if existing is not None:
                    # Refreshing in place keeps a phase drag with many integrals smooth.
                    if existing.text() != text:
                        existing.setText(text)
                    if column == VALUE_COLUMN:
                        existing.setFont(bold if row == ref_index else self.font())
                    continue
                item = QTableWidgetItem(text)
                if column == VALUE_COLUMN:
                    item.setFlags(read_only | Qt.ItemFlag.ItemIsEditable)
                    if row == ref_index:
                        item.setFont(bold)
                else:
                    item.setFlags(read_only)
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        if 0 <= selected < len(integrals):
            self.table.selectRow(selected)
        self.table.blockSignals(False)
        self._update_buttons()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != VALUE_COLUMN:
            return
        try:
            value = float(item.text().replace(",", "."))
        except ValueError:
            value = 0.0
        if value > 0:
            self.reference_changed.emit(item.row(), value)
        else:
            # Not a usable number: put the old text back.
            self.set_integrals(self._integrals, self._ref_index)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0 and self.table.selectedItems():
            self.delete_requested.emit(row)

    def _update_buttons(self) -> None:
        self.delete_button.setEnabled(bool(self.table.selectedItems()))
        self.clear_button.setEnabled(self.table.rowCount() > 0)
