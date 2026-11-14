"""Main application window."""

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from nmr import __version__
from nmr.core.dataset import Dataset
from nmr.core.io import LoadError, load
from nmr.core.processing import (
    ProcessingParams,
    auto_phase,
    default_params,
    process,
    shift_reference,
)
from nmr.gui.processing_panel import ProcessingPanel
from nmr.gui.shortcuts_dialog import ShortcutsDialog
from nmr.gui.spectrum_view import WHEEL_STEP, SpectrumView, Tool, format_nucleus

FILE_FILTER = "NMR data (*.dx *.jdx *.jcamp fid 1r);;All files (*)"

TOOL_HINTS = {
    Tool.SELECT: "",
    Tool.ZOOM: "Zoom ({mode}): drag to select a region. Press Z again to change the direction.",
    Tool.PAN: "Pan ({mode}): drag to move the spectrum. Press P again to change the direction.",
    Tool.CROSSHAIR: "Crosshair: drag to measure a distance.",
    Tool.PHASE: (
        "Manual phase: drag up/down for PH0, right-drag or Ctrl+drag for PH1, "
        "click to set the pivot. Hold Shift for fine steps."
    ),
    Tool.REFERENCE: "Reference: click a signal to set its chemical shift.",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("nmr")
        self.resize(1280, 760)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self.dataset: Dataset | None = None
        """The data as loaded from disk; never modified."""
        self.params = ProcessingParams()
        self.spectrum: Dataset | None = None
        """`dataset` processed with `params`."""
        self._undo: list[ProcessingParams] = []
        self._redo: list[ProcessingParams] = []

        self.plot = SpectrumView()
        self.setCentralWidget(self.plot)
        self.plot.cursor_moved.connect(self._show_cursor)
        self.plot.distance_measured.connect(self._show_distance)
        self.plot.phase_drag_started.connect(self._record_undo)
        self.plot.phase_dragged.connect(self._on_phase_dragged)
        self.plot.pivot_picked.connect(self._set_pivot)
        self.plot.reference_picked.connect(self._reference_at)

        self.panel = ProcessingPanel()
        self.panel.params_changed.connect(self.set_params)
        self.panel.auto_phase_requested.connect(self.auto_phase)
        self.dock = QDockWidget("PROCESSING", self)
        self.dock.setWidget(self.panel)
        self.dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

        self._info = QLabel("No data loaded")
        self._hint = QLabel()
        self._cursor = QLabel()
        self.statusBar().addWidget(self._info)
        self.statusBar().addWidget(self._hint, 1)
        self.statusBar().addPermanentWidget(self._cursor)
        self.statusBar().setSizeGripEnabled(False)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._update_enabled()

    # ---- data and processing ----------------------------------------------------------

    def open_path(self, path: str | Path) -> bool:
        """Load a file or folder and show it. Returns False (after telling the user) on failure."""
        try:
            dataset = load(path)
        except LoadError as exc:
            QMessageBox.warning(self, "Could not open", str(exc))
            return False

        self.dataset = dataset
        self._undo.clear()
        self._redo.clear()
        is_fid = dataset.domain == "time"
        # A FID is transformed and phased right away; a finished spectrum is shown as it is.
        self.params = default_params(dataset) if is_fid else ProcessingParams()
        self.panel.set_capabilities(is_fid=is_fid, can_phase=np.iscomplexobj(dataset.data))
        self.show_fid_action.blockSignals(True)
        self.show_fid_action.setChecked(False)
        self.show_fid_action.blockSignals(False)
        if is_fid:
            self.auto_phase(keep_view=False, record=False)
        else:
            self._reprocess(keep_view=False)
        self.setWindowTitle(f"{dataset.title} – nmr" if dataset.title else "nmr")
        self._update_enabled()
        return True

    def set_params(
        self, params: ProcessingParams, *, record: bool = True, keep_view: bool = True
    ) -> None:
        """Apply new processing settings. With `record` the old ones go on the undo stack."""
        if self.dataset is None or params == self.params:
            return
        if record:
            self._record_undo()
        self.params = params
        self._reprocess(keep_view=keep_view)

    def auto_phase(self, *, keep_view: bool = True, record: bool = True) -> None:
        if self.dataset is None or not np.iscomplexobj(self.dataset.data):
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            params = auto_phase(self.dataset, self.params)
        finally:
            QApplication.restoreOverrideCursor()
        if record:
            self._record_undo()
        self.params = params
        self._reprocess(keep_view=keep_view)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self.params)
            self.params = self._undo.pop()
            self._reprocess(keep_view=True)

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self.params)
            self.params = self._redo.pop()
            self._reprocess(keep_view=True)

    def _record_undo(self) -> None:
        self._undo.append(self.params)
        self._redo.clear()
        self._update_enabled()

    def _reprocess(self, *, keep_view: bool) -> None:
        self.spectrum = process(self.dataset, self.params)
        self.panel.set_params(self.params)
        self.plot.set_pivot(self.params.pivot_ppm)
        self._refresh_plot(keep_view=keep_view)
        self._update_enabled()

    def _refresh_plot(self, *, keep_view: bool) -> None:
        shown = self.dataset if self.show_fid_action.isChecked() else self.spectrum
        self.plot.set_dataset(shown, keep_view=keep_view)
        self._info.setText(_describe(shown))
        self._cursor.clear()

    @property
    def _showing_spectrum(self) -> bool:
        return self.spectrum is not None and not self.show_fid_action.isChecked()

    # ---- tools ------------------------------------------------------------------------

    def set_tool(self, tool: Tool) -> None:
        """Activate a mouse tool. Choosing zoom or pan again cycles its direction."""
        if tool is self.plot.tool and tool is Tool.ZOOM:
            self.plot.cycle_zoom_mode()
        elif tool is self.plot.tool and tool is Tool.PAN:
            self.plot.cycle_pan_mode()
        self.plot.set_tool(tool)
        self.tool_actions[tool].setChecked(True)
        mode = self.plot.zoom_mode if tool is Tool.ZOOM else self.plot.pan_mode
        self._hint.setText(TOOL_HINTS[tool].format(mode=mode))

    def _on_phase_dragged(self, d_ph0: float, d_ph1: float) -> None:
        if not self._showing_spectrum:
            return
        params = replace(
            self.params,
            ph0_deg=self.params.ph0_deg + d_ph0,
            ph1_deg=self.params.ph1_deg + d_ph1,
        )
        self.set_params(params, record=False)

    def _set_pivot(self, ppm: float) -> None:
        if not self._showing_spectrum:
            return
        # Moving the pivot must not change the look of the spectrum, so ph0 absorbs
        # the phase that ph1 contributes at the new position.
        old = self.params.pivot_ppm
        if old is None:
            old = self.spectrum.offset_ppm - self.spectrum.sw_ppm / 2
        ph0 = self.params.ph0_deg + self.params.ph1_deg * (old - ppm) / self.spectrum.sw_ppm
        self.set_params(replace(self.params, pivot_ppm=ppm, ph0_deg=ph0))

    def _reference_at(self, ppm: float) -> None:
        if not self._showing_spectrum:
            return
        peak = self._nearest_peak(ppm)
        suggestion = 0.0 if abs(peak) < 0.5 else round(peak, 2)
        value, accepted = QInputDialog.getDouble(
            self,
            "Reference",
            f"Signal at {peak:.4f} ppm.\nNew chemical shift (ppm):",
            suggestion,
            -10000.0,
            10000.0,
            4,
        )
        if accepted:
            self.set_params(shift_reference(self.params, value - peak))

    def _nearest_peak(self, ppm: float) -> float:
        """Top of the signal the user clicked on: the maximum within 1 % of the view."""
        low, high = self.plot.vb.viewRange()[0]
        tolerance = 0.01 * (high - low)
        axis = self.spectrum.ppm_axis
        window = np.abs(axis - ppm) <= tolerance
        if not window.any():
            return ppm
        return float(axis[window][np.argmax(self.spectrum.data.real[window])])

    def _show_cursor(self, x: float) -> None:
        if self._showing_spectrum:
            hz = x * self.spectrum.ref_freq_mhz
            self._cursor.setText(f"{x:.4f} ppm   {hz:.2f} Hz")
        else:
            self._cursor.setText(f"{x:.5f} s")

    def _show_distance(self, start: float, end: float) -> None:
        delta = abs(end - start)
        if self._showing_spectrum:
            hz = delta * self.spectrum.ref_freq_mhz
            self._hint.setText(f"Δ = {delta:.4f} ppm = {hz:.2f} Hz")
        else:
            self._hint.setText(f"Δ = {delta:.5f} s")

    def copy_image(self) -> None:
        QApplication.clipboard().setPixmap(self.plot.grab())
        self._hint.setText("Spectrum copied to the clipboard.")

    # ---- actions, menus, toolbar --------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, *, tip: str = "", checkable=False):
        action = QAction(text, self)
        if shortcut is not None:
            shortcuts = shortcut if isinstance(shortcut, list) else [shortcut]
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
            keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            tip = f"{tip or text.replace('&', '').rstrip('…')} ({keys})"
        if tip:
            action.setToolTip(tip)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        std = QKeySequence.StandardKey
        self.open_file_action = self._action("&Open File…", self._choose_file, std.Open)
        self.open_folder_action = self._action(
            "Open &Bruker Folder…", self._choose_folder, "Ctrl+Shift+O"
        )
        self.quit_action = self._action("&Quit", self.close, "Ctrl+Q")

        self.undo_action = self._action("&Undo", self.undo, std.Undo)
        self.redo_action = self._action("&Redo", self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"])
        self.copy_action = self._action("&Copy as Image", self.copy_image, std.Copy)

        tools = [
            (Tool.SELECT, "&Select", "Esc", "Select tool: drag to move the spectrum"),
            (Tool.ZOOM, "&Zoom", "Z", "Zoom in: drag to select a region"),
            (Tool.PAN, "&Pan", "P", "Pan the spectrum"),
            (Tool.CROSSHAIR, "&Crosshair", "C", "Crosshair cursor for measuring distances"),
            (Tool.PHASE, "&Manual Phase", "Shift+P", "Manual phase correction"),
            (Tool.REFERENCE, "&Reference", "L", "Set the chemical shift reference"),
        ]
        group = QActionGroup(self)
        self.tool_actions: dict[Tool, QAction] = {}
        for tool, text, key, tip in tools:
            action = self._action(
                text, lambda _=False, t=tool: self.set_tool(t), key, tip=tip, checkable=True
            )
            group.addAction(action)
            self.tool_actions[tool] = action
        self.tool_actions[Tool.SELECT].setChecked(True)

        plot = self.plot
        self.zoom_out_action = self._action("Zoom &Out", plot.zoom_out, "Shift+Z")
        self.full_action = self._action("&Full Spectrum", plot.show_full, "F")
        self.fit_action = self._action(
            "Fit to &Highest Intensity", plot.fit_height, "H", tip="Fit to highest intensity"
        )
        self.bigger_action = self._action(
            "&Increase Intensity", lambda: plot.scale_intensity(WHEEL_STEP), ["+", "="]
        )
        self.smaller_action = self._action(
            "&Decrease Intensity", lambda: plot.scale_intensity(1 / WHEEL_STEP), "-"
        )
        self.show_fid_action = self._action(
            "Show &FID", lambda: None, "Ctrl+F", tip="Show the FID", checkable=True
        )
        self.show_fid_action.toggled.connect(lambda: self._refresh_plot(keep_view=False))
        self.auto_phase_action = self._action(
            "&Automatic Phase Correction", lambda: self.auto_phase(), "Ctrl+Shift+P"
        )
        self.shortcuts_action = self._action("&Keyboard Shortcuts", self._show_shortcuts, "F1")
        self.about_action = self._action("&About nmr", self._show_about)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.open_file_action, self.open_folder_action])
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addAction(self.copy_action)

        view_menu = bar.addMenu("&View")
        view_menu.addActions([self.full_action, self.fit_action, self.zoom_out_action])
        view_menu.addActions([self.bigger_action, self.smaller_action])
        view_menu.addSeparator()
        view_menu.addAction(self.show_fid_action)
        panel_action = self.dock.toggleViewAction()
        panel_action.setText("&Processing Panel")
        view_menu.addAction(panel_action)

        tools_menu = bar.addMenu("&Tools")
        tools_menu.addActions(list(self.tool_actions.values())[:4])
        tools_menu.addSeparator()
        tools_menu.addActions(list(self.tool_actions.values())[4:])

        processing_menu = bar.addMenu("&Processing")
        processing_menu.addAction(self.auto_phase_action)
        processing_menu.addAction(self.tool_actions[Tool.PHASE])
        processing_menu.addAction(self.tool_actions[Tool.REFERENCE])

        help_menu = bar.addMenu("&Help")
        help_menu.addActions([self.shortcuts_action, self.about_action])

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Tools", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.toggleViewAction().setVisible(False)
        self.addToolBar(toolbar)

        def add(action: QAction, label: str) -> None:
            action.setIconText(label)
            toolbar.addAction(action)

        add(self.open_file_action, "Open")
        toolbar.addSeparator()
        for tool, label in (
            (Tool.SELECT, "Select"),
            (Tool.ZOOM, "Zoom"),
            (Tool.PAN, "Pan"),
            (Tool.CROSSHAIR, "Crosshair"),
        ):
            add(self.tool_actions[tool], label)
        toolbar.addSeparator()
        add(self.full_action, "Full")
        add(self.fit_action, "Fit height")
        toolbar.addSeparator()
        add(self.auto_phase_action, "Auto phase")
        add(self.tool_actions[Tool.PHASE], "Phase")
        add(self.tool_actions[Tool.REFERENCE], "Reference")
        toolbar.addSeparator()
        add(self.show_fid_action, "FID")

    def _update_enabled(self) -> None:
        loaded = self.dataset is not None
        is_fid = loaded and self.dataset.domain == "time"
        complex_data = loaded and np.iscomplexobj(self.dataset.data)
        for action in (
            self.copy_action,
            self.zoom_out_action,
            self.full_action,
            self.fit_action,
            self.bigger_action,
            self.smaller_action,
            self.tool_actions[Tool.REFERENCE],
        ):
            action.setEnabled(loaded)
        self.show_fid_action.setEnabled(is_fid)
        self.auto_phase_action.setEnabled(complex_data)
        self.tool_actions[Tool.PHASE].setEnabled(complex_data)
        self.undo_action.setEnabled(bool(self._undo))
        self.redo_action.setEnabled(bool(self._redo))

    # ---- dialogs and events -------------------------------------------------------------

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", FILE_FILTER)
        if path:
            self.open_path(path)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Bruker Folder")
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_path(urls[0].toLocalFile())

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About nmr",
            f"<b>nmr {__version__}</b><br>Open-source NMR processing and analysis."
            "<br><br>Free software under the GNU General Public License v3 or later.",
        )


def _describe(dataset: Dataset) -> str:
    parts = [
        format_nucleus(dataset.nucleus),
        f"{dataset.obs_freq_mhz:.2f} MHz",
        "FID" if dataset.domain == "time" else "Spectrum",
        f"{dataset.size:,} points",
        dataset.solvent,
    ]
    return "   ·   ".join(p for p in parts if p)
