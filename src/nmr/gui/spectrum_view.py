"""The plot area showing one FID or spectrum, and the mouse tools that act on it."""

from enum import Enum

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel

from nmr.core.dataset import Dataset
from nmr.gui import theme
from nmr.gui.integral_layer import IntegralLayer

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

WHEEL_STEP = 1.15
"""Intensity change per mouse-wheel notch."""
PH0_DEG_PER_PIXEL = 0.25
PH1_DEG_PER_PIXEL = 1.0


def format_nucleus(nucleus: str) -> str:
    """'13C' -> '¹³C'."""
    digits = len(nucleus) - len(nucleus.lstrip("0123456789"))
    return nucleus[:digits].translate(_SUPERSCRIPT) + nucleus[digits:]


class Tool(Enum):
    SELECT = "select"
    ZOOM = "zoom"
    PAN = "pan"
    CROSSHAIR = "crosshair"
    PHASE = "phase"
    REFERENCE = "reference"
    INTEGRATE = "integrate"


ZOOM_MODES = ("horizontal", "vertical", "box")
PAN_MODES = ("free", "horizontal", "vertical")

_CURSORS = {
    Tool.SELECT: Qt.CursorShape.ArrowCursor,
    Tool.ZOOM: Qt.CursorShape.CrossCursor,
    Tool.PAN: Qt.CursorShape.OpenHandCursor,
    Tool.CROSSHAIR: Qt.CursorShape.CrossCursor,
    Tool.PHASE: Qt.CursorShape.SizeVerCursor,
    Tool.REFERENCE: Qt.CursorShape.PointingHandCursor,
    Tool.INTEGRATE: Qt.CursorShape.SplitHCursor,
}


class _ViewBox(pg.ViewBox):
    """Forwards mouse input to the SpectrumView, which decides by the active tool."""

    def __init__(self) -> None:
        super().__init__(enableMenu=False)
        self.handler: SpectrumView | None = None

    def wheelEvent(self, ev, axis=None) -> None:
        self.handler.on_wheel(ev)

    def mouseDragEvent(self, ev, axis=None) -> None:
        self.handler.on_drag(ev)

    def mouseClickEvent(self, ev) -> None:
        self.handler.on_click(ev)


class SpectrumView(pg.PlotWidget):
    cursor_moved = Signal(float)
    """Mouse position on the x axis (ppm or seconds)."""
    distance_measured = Signal(float, float)
    """Start and end of a crosshair drag on the x axis."""
    phase_drag_started = Signal()
    phase_dragged = Signal(float, float)
    """Change of (ph0, ph1) in degrees since the last event."""
    pivot_picked = Signal(float)
    reference_picked = Signal(float)
    region_selected = Signal(float, float)
    """Both ends of a region dragged with the integrate tool."""

    def __init__(self) -> None:
        view_box = _ViewBox()
        super().__init__(viewBox=view_box, background="w")
        view_box.handler = self
        self.vb = view_box
        self.tool = Tool.SELECT
        self.zoom_mode = ZOOM_MODES[0]
        self.pan_mode = PAN_MODES[0]
        self._x_full: tuple[float, float] | None = None
        self._y: np.ndarray | None = None
        self._pivot_ppm: float | None = None

        self.hideAxis("left")
        self.hideButtons()
        self.getPlotItem().setContentsMargins(6, 10, 6, 2)
        axis = self.getAxis("bottom")
        axis.setPen(pg.mkPen(theme.AXIS, width=1))
        axis.setTextPen(pg.mkPen(theme.AXIS))
        axis.setTickFont(QFont(self.font().family(), 9))
        axis.setHeight(44)
        self.hideAxis("bottom")  # shown once data is loaded
        # NMR convention: chemical shift increases to the left.
        self.vb.invertX(True)

        # A pen wider than one pixel makes Qt draw the curve an order of magnitude
        # slower, which is felt as lag on every pan, zoom and phase step.
        self.curve = self.plot(pen=pg.mkPen(theme.SPECTRUM, width=1), antialias=True)
        # Keep interaction smooth with several hundred thousand points.
        self.curve.setDownsampling(auto=True, method="peak")
        self.curve.setClipToView(True)

        dashed = Qt.PenStyle.DashLine
        self._cross_v = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.CROSSHAIR, width=1))
        self._cross_h = pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.CROSSHAIR, width=1))
        self._anchor = pg.InfiniteLine(
            angle=90, pen=pg.mkPen(theme.CROSSHAIR, width=1, style=dashed)
        )
        self._pivot = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.PIVOT, width=1, style=dashed))
        for line in (self._cross_v, self._cross_h, self._anchor, self._pivot):
            line.setVisible(False)
            self.addItem(line, ignoreBounds=True)

        self._hint = QLabel(
            "Drop a Bruker folder or JCAMP-DX file here\nor press Ctrl+O to open one", self
        )
        self._hint.setObjectName("emptyHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.integrals = IntegralLayer(self)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # ---- data -------------------------------------------------------------------

    def set_dataset(self, dataset: Dataset, *, keep_view: bool = False) -> None:
        """Show `dataset`. With `keep_view` the current zoom is preserved."""
        self._hint.hide()
        self.showAxis("bottom")
        is_fid = dataset.domain == "time"
        self.vb.invertX(not is_fid)
        if is_fid:
            self.setLabel("bottom", "t / s")
        else:
            self.setLabel("bottom", f"δ({format_nucleus(dataset.nucleus)}) / ppm")
        x, y = dataset.x_axis, dataset.data.real
        if not is_fid:
            # pyqtgraph's clip-to-view needs ascending x; the inverted view flips it back.
            x, y = x[::-1], y[::-1]
        self._y = np.ascontiguousarray(y)
        self._x_full = (float(x[0]), float(x[-1]))
        self.curve.setData(np.ascontiguousarray(x), self._y)
        margin = 0.02 * (x[-1] - x[0])
        self.vb.setLimits(xMin=x[0] - margin, xMax=x[-1] + margin)
        if not keep_view:
            self.show_full()

    def clear_dataset(self) -> None:
        """Back to the empty state with the drop hint."""
        self._y = None
        self._x_full = None
        self.curve.setData([], [])
        self.hideAxis("bottom")
        self._hint.show()

    # ---- view commands ------------------------------------------------------------

    def show_full(self) -> None:
        """Whole x range, intensity fitted."""
        if self._x_full is None:
            return
        self.vb.setRange(xRange=self._x_full, padding=0.02)
        self.fit_height()

    def fit_height(self) -> None:
        """Scale the intensity so the tallest visible signal fills the window."""
        if self._y is None:
            return
        x = self.curve.getOriginalDataset()[0]
        low, high = self.vb.viewRange()[0]
        visible = self._y[np.searchsorted(x, low) : np.searchsorted(x, high) + 1]
        if not visible.size:
            return
        top, bottom = float(visible.max()), min(float(visible.min()), 0.0)
        span = max(top - bottom, 1e-12)
        # The room below the baseline holds the integral labels.
        self.vb.setRange(yRange=(bottom - 0.09 * span, top + 0.06 * span), padding=0)

    def scale_intensity(self, factor: float) -> None:
        """Multiply the displayed intensity; the zero line stays where it is."""
        x_centre = sum(self.vb.viewRange()[0]) / 2
        self.vb.scaleBy(y=1.0 / factor, center=pg.Point(x_centre, 0.0))

    def zoom_out(self) -> None:
        low, high = self.vb.viewRange()[0]
        self.vb.scaleBy(x=2.0, center=pg.Point((low + high) / 2, 0.0))

    # ---- tools --------------------------------------------------------------------

    def set_tool(self, tool: Tool) -> None:
        self.tool = tool
        self.vb.setCursor(_CURSORS[tool])
        crosshair = tool is Tool.CROSSHAIR
        self._cross_v.setVisible(crosshair)
        self._cross_h.setVisible(crosshair)
        self._anchor.setVisible(False)
        self._pivot.setVisible(tool is Tool.PHASE and self._pivot_ppm is not None)

    def set_pivot(self, ppm: float | None) -> None:
        self._pivot_ppm = ppm
        if ppm is not None:
            self._pivot.setValue(ppm)
        self._pivot.setVisible(self.tool is Tool.PHASE and ppm is not None)

    def cycle_zoom_mode(self) -> str:
        self.zoom_mode = ZOOM_MODES[(ZOOM_MODES.index(self.zoom_mode) + 1) % len(ZOOM_MODES)]
        return self.zoom_mode

    def cycle_pan_mode(self) -> str:
        self.pan_mode = PAN_MODES[(PAN_MODES.index(self.pan_mode) + 1) % len(PAN_MODES)]
        return self.pan_mode

    # ---- mouse input (called by the view box) ---------------------------------------

    def on_wheel(self, ev) -> None:
        ev.accept()
        factor = WHEEL_STEP ** (ev.delta() / 120.0)
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.vb.scaleBy(x=1.0 / factor, center=self.vb.mapToView(ev.pos()))
        else:
            self.scale_intensity(factor)

    def on_click(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x = self.vb.mapToView(ev.pos()).x()
        if self.tool is Tool.PHASE:
            ev.accept()
            self.pivot_picked.emit(x)
        elif self.tool is Tool.REFERENCE:
            ev.accept()
            self.reference_picked.emit(x)

    def on_drag(self, ev) -> None:
        left = ev.button() == Qt.MouseButton.LeftButton
        if self.tool is Tool.PHASE and (left or ev.button() == Qt.MouseButton.RightButton):
            self._drag_phase(ev, first_order=not left)
        elif not left:
            ev.ignore()
        elif self.tool is Tool.ZOOM:
            self._drag_zoom(ev)
        elif self.tool is Tool.INTEGRATE:
            self._drag_integrate(ev)
        elif self.tool is Tool.CROSSHAIR:
            self._drag_measure(ev)
        elif self.tool in (Tool.SELECT, Tool.PAN):
            self._drag_pan(ev, self.pan_mode if self.tool is Tool.PAN else "free")
        else:
            ev.ignore()

    def _drag_zoom(self, ev) -> None:
        horizontal = self.zoom_mode in ("horizontal", "box")
        vertical = self.zoom_mode in ("vertical", "box")
        target = self._drag_band(ev, horizontal=horizontal, vertical=vertical)
        if target is None:
            return
        ranges = {}
        if horizontal:
            ranges["xRange"] = sorted((target.left(), target.right()))
        if vertical:
            ranges["yRange"] = sorted((target.top(), target.bottom()))
        self.vb.setRange(padding=0, **ranges)

    def _drag_integrate(self, ev) -> None:
        target = self._drag_band(ev, horizontal=True, vertical=False)
        if target is not None:
            self.region_selected.emit(target.left(), target.right())

    def _drag_band(self, ev, *, horizontal: bool, vertical: bool) -> QRectF | None:
        """Rubber-band selection. Returns the selected view rectangle when the drag ends."""
        ev.accept()
        start, end = ev.buttonDownPos(Qt.MouseButton.LeftButton), ev.pos()
        bounds = self.vb.boundingRect()
        p1 = QPointF(start.x() if horizontal else bounds.left(), start.y() if vertical else 0.0)
        p2 = QPointF(
            end.x() if horizontal else bounds.right(), end.y() if vertical else bounds.height()
        )
        if not ev.isFinish():
            self.vb.updateScaleBox(p1, p2)
            return None
        self.vb.rbScaleBox.hide()
        if (horizontal and abs(p1.x() - p2.x()) < 4) or (vertical and abs(p1.y() - p2.y()) < 4):
            return None
        return self.vb.childGroup.mapRectFromParent(QRectF(p1, p2).normalized())

    def _drag_pan(self, ev, mode: str) -> None:
        ev.accept()
        move = QPointF(ev.lastPos() - ev.pos())
        if mode == "horizontal":
            move.setY(0.0)
        elif mode == "vertical":
            move.setX(0.0)
        to_view = pg.functions.invertQTransform(self.vb.childGroup.transform())
        shift = to_view.map(move) - to_view.map(QPointF(0.0, 0.0))
        self.vb.translateBy(x=shift.x(), y=shift.y())

    def _drag_measure(self, ev) -> None:
        ev.accept()
        start = self.vb.mapToView(ev.buttonDownPos(Qt.MouseButton.LeftButton)).x()
        end = self.vb.mapToView(ev.pos())
        self._anchor.setValue(start)
        self._anchor.setVisible(True)
        self._cross_v.setValue(end.x())
        self._cross_h.setValue(end.y())
        self.distance_measured.emit(start, end.x())

    def _drag_phase(self, ev, *, first_order: bool) -> None:
        ev.accept()
        if ev.isStart():
            self.phase_drag_started.emit()
        first_order = first_order or bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
        fine = 0.1 if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        up = (ev.lastPos().y() - ev.pos().y()) * fine
        if first_order:
            self.phase_dragged.emit(0.0, up * PH1_DEG_PER_PIXEL)
        else:
            self.phase_dragged.emit(up * PH0_DEG_PER_PIXEL, 0.0)

    def _on_mouse_moved(self, scene_pos) -> None:
        if self._y is None or not self.vb.sceneBoundingRect().contains(scene_pos):
            return
        point = self.vb.mapSceneToView(scene_pos)
        if self.tool is Tool.CROSSHAIR:
            self._cross_v.setValue(point.x())
            self._cross_h.setValue(point.y())
        self.cursor_moved.emit(point.x())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Qt already sends resize events while the base class is still being set up.
        hint = getattr(self, "_hint", None)
        if hint is not None:
            hint.setGeometry(self.rect())
