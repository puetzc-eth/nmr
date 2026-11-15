"""Draws integrals on top of the spectrum: the running-integral curve, a bracket under
the baseline marking the region, and the normalised value."""

import numpy as np
import pyqtgraph as pg

from nmr.core.dataset import Dataset
from nmr.core.integration import Integral, running_integral
from nmr.gui import theme

CURVE_BOTTOM = 0.28
"""Where integral curves start, as a fraction of the plot height."""
CURVE_HEIGHT = 0.45
"""Height of the largest integral curve, as a fraction of the plot height."""
MAX_CURVE_POINTS = 400
LABEL_HEIGHT_PX = 20
TICK_PX = 5


class IntegralLayer:
    """Integral curves keep their size on screen when the intensity is rescaled, so
    they are laid out again whenever the vertical view changes."""

    def __init__(self, plot: pg.PlotWidget) -> None:
        self._plot = plot
        self._vb = plot.getViewBox()
        self._items: list[tuple[pg.PlotCurveItem, pg.PlotCurveItem, pg.TextItem]] = []
        self._data: list[tuple[Integral, np.ndarray, np.ndarray]] = []
        self._laid_out_for: tuple | None = None
        self._vb.sigRangeChanged.connect(self._on_range_changed)

    def __len__(self) -> int:
        return len(self._data)

    def set(self, spectrum: Dataset | None, integrals: list[Integral]) -> None:
        if spectrum is None:
            integrals = []
        # Graphics items are reused: creating them is slow, and this runs on every
        # step of a phase drag.
        pen = pg.mkPen(theme.INTEGRAL, width=1)
        while len(self._items) < len(integrals):
            curve = pg.PlotCurveItem(pen=pen, antialias=True)
            bracket = pg.PlotCurveItem(pen=pen)
            label = pg.TextItem(color=theme.INTEGRAL, anchor=(0.5, 1.0))
            for item in (curve, bracket, label):
                self._plot.addItem(item, ignoreBounds=True)
            self._items.append((curve, bracket, label))
        while len(self._items) > len(integrals):
            for item in self._items.pop():
                self._plot.removeItem(item)

        self._data = []
        for integral, (_, _, label) in zip(integrals, self._items, strict=True):
            ppm, running = running_integral(spectrum, integral.high_ppm, integral.low_ppm)
            step = max(1, ppm.size // MAX_CURVE_POINTS)
            self._data.append((integral, ppm[::step], running[::step]))
            text = f"{integral.value:.2f}"
            if label.toPlainText() != text:
                label.setText(text)
        self._layout()

    def _on_range_changed(self) -> None:
        # Panning sideways changes nothing about the layout.
        if self._data and self._vertical_view() != self._laid_out_for:
            self._layout()

    def _vertical_view(self) -> tuple:
        bottom, top = self._vb.viewRange()[1]
        return bottom, top, self._vb.height()

    def _layout(self) -> None:
        self._laid_out_for = self._vertical_view()
        if not self._data:
            return
        bottom, top, _ = self._laid_out_for
        height = top - bottom
        pixel = self._vb.viewPixelSize()[1]
        largest = max(abs(integral.area) for integral, _, _ in self._data) or 1.0
        bracket_y = bottom + LABEL_HEIGHT_PX * pixel
        tick = bracket_y + TICK_PX * pixel
        for (integral, ppm, running), (curve, bracket, label) in zip(
            self._data, self._items, strict=True
        ):
            scaled = bottom + height * (CURVE_BOTTOM + CURVE_HEIGHT * running / largest)
            curve.setData(ppm, scaled)
            high, low = integral.high_ppm, integral.low_ppm
            bracket.setData([high, high, low, low], [tick, bracket_y, bracket_y, tick])
            label.setPos((high + low) / 2, bottom)
