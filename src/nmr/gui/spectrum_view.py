"""The plot area showing one FID or spectrum."""

import numpy as np
import pyqtgraph as pg

from nmr.core.dataset import Dataset

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def format_nucleus(nucleus: str) -> str:
    """'13C' -> '¹³C'."""
    digits = len(nucleus) - len(nucleus.lstrip("0123456789"))
    return nucleus[:digits].translate(_SUPERSCRIPT) + nucleus[digits:]


class SpectrumView(pg.PlotWidget):
    def __init__(self) -> None:
        super().__init__(background="w")
        self.hideAxis("left")
        self.setLabel("bottom", "δ / ppm")
        # NMR convention: chemical shift increases to the left.
        self.getViewBox().invertX(True)

        self.curve = self.plot(pen=pg.mkPen("#1f4e9c", width=1))
        # Keep interaction smooth with several hundred thousand points.
        self.curve.setDownsampling(auto=True, method="peak")
        self.curve.setClipToView(True)

    def set_dataset(self, dataset: Dataset) -> None:
        is_fid = dataset.domain == "time"
        self.getViewBox().invertX(not is_fid)
        if is_fid:
            self.setLabel("bottom", "t / s")
        else:
            self.setLabel("bottom", f"δ({format_nucleus(dataset.nucleus)}) / ppm")
        x, y = dataset.x_axis, dataset.data.real
        if not is_fid:
            # pyqtgraph's clip-to-view needs ascending x; the inverted view flips it back.
            x, y = x[::-1], y[::-1]
        self.curve.setData(np.ascontiguousarray(x), np.ascontiguousarray(y))
        self.getViewBox().setRange(xRange=(x[0], x[-1]), yRange=(y.min(), y.max()), padding=0.02)
