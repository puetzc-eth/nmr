"""Draws multiplets above the spectrum: a bracket with a tick for every line, and a
label with shift, pattern and number of nuclei."""

import numpy as np
import pyqtgraph as pg

from nmr.core.multiplets import Multiplet
from nmr.gui import theme

BAND_PX = 96
"""Height of the strip at the top of the plot that holds the labels."""
TICK_PX = 6


def label_text(multiplet: Multiplet, element: str) -> str:
    return f"{multiplet.shift_ppm:.2f} ({multiplet.pattern}, {multiplet.nuclei}{element})"


class MultipletLayer:
    """Labels keep their place at the top of the plot, so the layout is redone
    whenever the vertical view changes."""

    def __init__(self, plot: pg.PlotWidget) -> None:
        self._plot = plot
        self._vb = plot.getViewBox()
        self._items: list[tuple[pg.PlotCurveItem, pg.TextItem]] = []
        self._multiplets: list[Multiplet] = []
        self._laid_out_for: tuple | None = None
        self._vb.sigRangeChanged.connect(self._on_range_changed)

    def __len__(self) -> int:
        return len(self._multiplets)

    def set(self, multiplets: list[Multiplet], element: str = "H") -> None:
        pen = pg.mkPen(theme.MULTIPLET, width=1)
        while len(self._items) < len(multiplets):
            bracket = pg.PlotCurveItem(pen=pen, connect="pairs")
            # Vertical text: neighbouring multiplets do not run into each other.
            label = pg.TextItem(color=theme.MULTIPLET, anchor=(1.0, 0.5), angle=90)
            for item in (bracket, label):
                self._plot.addItem(item, ignoreBounds=True)
            self._items.append((bracket, label))
        while len(self._items) > len(multiplets):
            for item in self._items.pop():
                self._plot.removeItem(item)

        self._multiplets = list(multiplets)
        for multiplet, (_, label) in zip(multiplets, self._items, strict=True):
            text = label_text(multiplet, element)
            if label.toPlainText() != text:
                label.setText(text)
        self._layout()

    def _on_range_changed(self) -> None:
        if self._multiplets and self._vertical_view() != self._laid_out_for:
            self._layout()

    def _vertical_view(self) -> tuple:
        bottom, top = self._vb.viewRange()[1]
        return bottom, top, self._vb.height()

    def _layout(self) -> None:
        self._laid_out_for = self._vertical_view()
        if not self._multiplets:
            return
        _, top, _ = self._laid_out_for
        pixel = self._vb.viewPixelSize()[1]
        bracket_y = top - BAND_PX * pixel
        tick_y = bracket_y - TICK_PX * pixel
        for multiplet, (bracket, label) in zip(self._multiplets, self._items, strict=True):
            # One horizontal line over the region, and a short tick down at every line.
            x = [multiplet.high_ppm, multiplet.low_ppm]
            y = [bracket_y, bracket_y]
            for peak in multiplet.peaks_ppm:
                x += [peak, peak]
                y += [bracket_y, tick_y]
            bracket.setData(np.array(x), np.array(y))
            label.setPos(multiplet.shift_ppm, top - 4 * pixel)
