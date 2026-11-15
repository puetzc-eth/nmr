"""Left sidebar: the spectra of the document, each with a small preview."""

import numpy as np
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from nmr.core.dataset import Dataset
from nmr.gui import theme
from nmr.gui.spectrum_view import format_nucleus

THUMBNAIL = QSize(200, 70)


def thumbnail(spectrum: Dataset, size: QSize = THUMBNAIL) -> QPixmap:
    """A small picture of a spectrum: one min/max pair per pixel column."""
    pixmap = QPixmap(size)
    pixmap.fill(QColor("white"))
    real = spectrum.data.real
    width, height = size.width(), size.height()
    columns = min(width, real.size)
    if columns < 2:
        return pixmap
    usable = real[: real.size - real.size % columns].reshape(columns, -1)
    low, high = usable.min(axis=1), usable.max(axis=1)
    bottom, top = min(float(low.min()), 0.0), float(high.max())
    span = (top - bottom) or 1.0
    x = np.repeat(np.linspace(1.0, width - 2.0, columns), 2)
    y = np.column_stack((low, high)).ravel()
    y = (height - 4.0) - (y - bottom) / span * (height - 8.0)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(theme.SPECTRUM), 1))
    painter.drawPolyline(QPolygonF([QPointF(a, b) for a, b in zip(x, y, strict=True)]))
    painter.end()
    return pixmap


class SpectraPanel(QWidget):
    current_changed = Signal(int)
    remove_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setFlow(QListView.Flow.TopToBottom)
        self.list.setWrapping(False)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setIconSize(THUMBNAIL)
        self.list.setSpacing(6)
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setWordWrap(False)
        self.list.currentRowChanged.connect(self._on_row_changed)

        delete_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.list)
        delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_key.activated.connect(self._remove_current)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 12)
        layout.addWidget(self.list)
        self.setFixedWidth(THUMBNAIL.width() + 52)

    def set_spectra(self, spectra: list[Dataset], current: int) -> None:
        """Rebuild the list from the processed spectra of the document."""
        self.list.blockSignals(True)
        self.list.clear()
        for spectrum in spectra:
            item = QListWidgetItem(_icon(spectrum), _label(spectrum))
            item.setToolTip(spectrum.title)
            item.setSizeHint(QSize(THUMBNAIL.width() + 16, THUMBNAIL.height() + 34))
            self.list.addItem(item)
        self.list.setCurrentRow(current)
        self.list.blockSignals(False)

    def update_spectrum(self, index: int, spectrum: Dataset) -> None:
        item = self.list.item(index)
        if item is not None:
            item.setIcon(_icon(spectrum))

    def set_current(self, index: int) -> None:
        self.list.blockSignals(True)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.current_changed.emit(row)

    def _remove_current(self) -> None:
        if self.list.currentRow() >= 0:
            self.remove_requested.emit(self.list.currentRow())


def _icon(spectrum: Dataset) -> QIcon:
    pixmap = thumbnail(spectrum)
    icon = QIcon(pixmap)
    # Without this Qt tints the preview of the selected spectrum blue.
    icon.addPixmap(pixmap, QIcon.Mode.Selected)
    return icon


def _label(spectrum: Dataset) -> str:
    title = spectrum.title.split(" | ")[0] if spectrum.title else "Untitled"
    return f"{format_nucleus(spectrum.nucleus)}  {title}".strip()
