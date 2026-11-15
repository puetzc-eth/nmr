"""Side panel with the processing settings of the current data set."""

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from nmr.core.processing import ProcessingParams

ZERO_FILL_FACTORS = (1, 2, 4, 8)
DEFAULT_BASELINE_ORDER = 3


class ProcessingPanel(QWidget):
    params_changed = Signal(object)
    """Emitted with the new ProcessingParams whenever the user edits a setting."""
    auto_phase_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._params = ProcessingParams()
        self.setMinimumWidth(270)

        self.lb = _spin(0.0, 100.0, 0.1, " Hz")
        self.lb.setToolTip("Exponential line broadening: less noise, wider lines")
        self.gb = _spin(0.0, 100.0, 0.1, " Hz")
        self.gb.setToolTip("Gaussian line broadening (full width at half maximum)")
        self.zero_fill = QComboBox()
        for factor in ZERO_FILL_FACTORS:
            self.zero_fill.addItem("Off" if factor == 1 else f"× {factor}", factor)
        self.zero_fill.setToolTip("Adds points to the spectrum for a smoother line shape")
        self.transform_group = QGroupBox("Fourier transform")
        transform = _form(self.transform_group)
        transform.addRow("Exponential (LB)", self.lb)
        transform.addRow("Gaussian (GB)", self.gb)
        transform.addRow("Zero filling", self.zero_fill)

        self.ph0 = _spin(-180.0, 180.0, 1.0, " °", wrapping=True)
        self.ph1 = _spin(-7200.0, 7200.0, 5.0, " °")
        self.auto_phase = QPushButton("Automatic")
        self.auto_phase.setToolTip("Find PH0 and PH1 automatically")
        self.phase_group = QGroupBox("Phase correction")
        phase = _form(self.phase_group)
        phase.addRow("Zero order (PH0)", self.ph0)
        phase.addRow("First order (PH1)", self.ph1)
        phase.addRow(self.auto_phase)

        self.baseline = QCheckBox("Subtract polynomial")
        self.baseline_order = QSpinBox()
        self.baseline_order.setRange(0, 9)
        self.baseline_order.setValue(DEFAULT_BASELINE_ORDER)
        self.baseline_group = QGroupBox("Baseline correction")
        baseline = _form(self.baseline_group)
        baseline.addRow(self.baseline)
        baseline.addRow("Order", self.baseline_order)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.setSpacing(6)
        for group in (self.transform_group, self.phase_group, self.baseline_group):
            layout.addWidget(group)
        # Take only the height the settings need; the rest goes to the panels below.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Each widget changes only its own setting, so the rounding of the displayed
        # numbers never leaks into the others.
        self.lb.valueChanged.connect(lambda v: self._change(lb_hz=v))
        self.gb.valueChanged.connect(lambda v: self._change(gb_hz=v))
        self.ph0.valueChanged.connect(lambda v: self._change(ph0_deg=v))
        self.ph1.valueChanged.connect(lambda v: self._change(ph1_deg=v))
        self.zero_fill.currentIndexChanged.connect(
            lambda: self._change(zero_fill_factor=self.zero_fill.currentData())
        )
        self.baseline.toggled.connect(self._change_baseline)
        self.baseline_order.valueChanged.connect(self._change_baseline)
        self.auto_phase.clicked.connect(self.auto_phase_requested)
        self.set_capabilities(is_fid=False, can_phase=False)
        self.setEnabled(False)

    def set_capabilities(self, *, is_fid: bool, can_phase: bool) -> None:
        """Enable only what applies: transform settings need a FID, phasing complex data."""
        self.setEnabled(True)
        self.transform_group.setEnabled(is_fid)
        self.phase_group.setEnabled(can_phase)

    def set_params(self, params: ProcessingParams) -> None:
        """Show `params` without emitting `params_changed`."""
        self._params = params
        widgets = (self.lb, self.gb, self.zero_fill, self.ph0, self.ph1)
        widgets += (self.baseline, self.baseline_order)
        for widget in widgets:
            widget.blockSignals(True)
        self.lb.setValue(params.lb_hz)
        self.gb.setValue(params.gb_hz)
        index = self.zero_fill.findData(params.zero_fill_factor)
        self.zero_fill.setCurrentIndex(max(index, 0))
        self.ph0.setValue((params.ph0_deg + 180.0) % 360.0 - 180.0)
        self.ph1.setValue(params.ph1_deg)
        self.baseline.setChecked(params.baseline_order is not None)
        if params.baseline_order is not None:
            self.baseline_order.setValue(params.baseline_order)
        self.baseline_order.setEnabled(self.baseline.isChecked())
        for widget in widgets:
            widget.blockSignals(False)

    def _change(self, **changes) -> None:
        self._params = replace(self._params, **changes)
        self.params_changed.emit(self._params)

    def _change_baseline(self) -> None:
        enabled = self.baseline.isChecked()
        self.baseline_order.setEnabled(enabled)
        self._change(baseline_order=self.baseline_order.value() if enabled else None)


def _form(group: QGroupBox) -> QFormLayout:
    form = QFormLayout(group)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(8)
    return form


def _spin(
    low: float, high: float, step: float, suffix: str, *, wrapping: bool = False
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setSuffix(suffix)
    spin.setWrapping(wrapping)
    spin.setKeyboardTracking(False)
    return spin
