"""Main application window."""

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTabBar,
    QTabWidget,
)

from nmr import __version__
from nmr.core.dataset import Dataset
from nmr.core.document import PROJECT_SUFFIX, Document, Entry
from nmr.core.integration import IntegralSet, evaluate
from nmr.core.io import LoadError
from nmr.core.io.export import save_csv, save_jcamp
from nmr.core.multiplets import MultipletSet, analyse, format_report
from nmr.core.processing import (
    ProcessingParams,
    auto_phase,
    fourier_transform,
    process,
    shift_reference,
)
from nmr.gui import icons
from nmr.gui.integrals_panel import IntegralsPanel
from nmr.gui.multiplets_panel import MultipletsPanel
from nmr.gui.processing_panel import ProcessingPanel
from nmr.gui.ribbon import Ribbon
from nmr.gui.shortcuts_dialog import ShortcutsDialog
from nmr.gui.spectra_panel import SpectraPanel
from nmr.gui.spectrum_view import WHEEL_STEP, SpectrumView, Tool, format_nucleus

SIDEBAR_WIDTH = 300
PROJECT_FILTER = f"nmr project (*{PROJECT_SUFFIX})"
OPEN_FILTER = (
    f"All supported (*{PROJECT_SUFFIX} *.dx *.jdx *.jcamp *.jdf *.zip fid 1r procpar);;"
    f"{PROJECT_FILTER};;JCAMP-DX (*.dx *.jdx *.jcamp);;JEOL Delta (*.jdf);;"
    "Bruker or Varian/Agilent FID (fid 1r procpar);;ZIP archive (*.zip);;All files (*)"
)
EXPORTERS = {
    "JCAMP-DX": ("JCAMP-DX (*.jdx)", ".jdx", save_jcamp),
    "CSV": ("Comma-separated values (*.csv)", ".csv", save_csv),
}

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
    Tool.MULTIPLET: (
        "Multiplets: drag across a signal. Correct Type or Nuclei in the table, "
        "select a row and press Delete to remove it."
    ),
    Tool.INTEGRATE: (
        "Integrate: drag across a signal. Edit a value in the table to normalise, "
        "select a row and press Delete to remove it."
    ),
}

Snapshot = tuple[ProcessingParams, IntegralSet, MultipletSet]


@dataclass
class _Session:
    """What the window keeps per spectrum while the document is open; never saved."""

    undo: list[Snapshot] = field(default_factory=list)
    redo: list[Snapshot] = field(default_factory=list)
    spectrum: Dataset | None = None
    transform_key: tuple | None = None
    transformed: Dataset | None = None


def _session(entry: Entry) -> _Session:
    return entry.runtime.setdefault("session", _Session())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.resize(1400, 800)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self.document = Document()
        self.current = -1
        """Index of the spectrum being shown, -1 if the document is empty."""
        self.modified = False

        self.plot = SpectrumView()
        self.setCentralWidget(self.plot)
        self.plot.cursor_moved.connect(self._show_cursor)
        self.plot.distance_measured.connect(self._show_distance)
        self.plot.phase_drag_started.connect(self._record_undo)
        self.plot.phase_dragged.connect(self._on_phase_dragged)
        self.plot.pivot_picked.connect(self._set_pivot)
        self.plot.reference_picked.connect(self._reference_at)
        self.plot.region_selected.connect(self._add_integral)
        self.plot.multiplet_selected.connect(self._add_multiplet)

        self.spectra_panel = SpectraPanel()
        self.spectra_panel.current_changed.connect(self.select)
        self.spectra_panel.remove_requested.connect(self.remove_spectrum)
        self.spectra_dock = self._add_dock(
            "SPECTRA", self.spectra_panel, Qt.DockWidgetArea.LeftDockWidgetArea
        )

        self.panel = ProcessingPanel()
        self.panel.params_changed.connect(self.set_params)
        self.panel.auto_phase_requested.connect(self.auto_phase)
        # Scrollable, so the settings never squeeze the integral table out of view.
        scroll = QScrollArea()
        scroll.setWidget(self.panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(SIDEBAR_WIDTH)
        self.dock = self._add_dock("PROCESSING", scroll)

        self.integrals_panel = IntegralsPanel()
        self.integrals_panel.setMinimumWidth(SIDEBAR_WIDTH)
        self.integrals_panel.reference_changed.connect(
            lambda index, value: self.set_integrals(self.integrals.with_reference(index, value))
        )
        self.integrals_panel.delete_requested.connect(
            lambda index: self.set_integrals(self.integrals.remove(index))
        )
        self.integrals_panel.clear_requested.connect(lambda: self.set_integrals(IntegralSet()))
        self.integrals_dock = self._add_dock("INTEGRALS", self.integrals_panel)
        self.multiplets_panel = MultipletsPanel()
        self.multiplets_panel.setMinimumWidth(SIDEBAR_WIDTH)
        self.multiplets_panel.pattern_changed.connect(
            lambda row, pattern: self.set_multiplets(self.multiplets.edited(row, pattern=pattern))
        )
        self.multiplets_panel.nuclei_changed.connect(
            lambda row, nuclei: self.set_multiplets(self.multiplets.edited(row, nuclei=nuclei))
        )
        self.multiplets_panel.delete_requested.connect(
            lambda row: self.set_multiplets(self.multiplets.remove(row))
        )
        self.multiplets_panel.clear_requested.connect(lambda: self.set_multiplets(MultipletSet()))
        self.multiplets_panel.copy_requested.connect(self.copy_report)
        self.multiplets_dock = self._add_dock("MULTIPLETS", self.multiplets_panel)
        # Integrals and multiplets share the lower right corner as two tabs.
        self.tabifyDockWidget(self.integrals_dock, self.multiplets_dock)
        self.setTabPosition(Qt.DockWidgetArea.RightDockWidgetArea, QTabWidget.TabPosition.North)
        self.integrals_dock.raise_()
        for bar in self.findChildren(QTabBar):
            if bar.parent() is self:
                # Show the full panel names instead of eliding them.
                bar.setElideMode(Qt.TextElideMode.ElideNone)
                bar.setExpanding(False)
        self.resizeDocks([self.dock, self.integrals_dock], [340, 400], Qt.Orientation.Vertical)

        self._info = QLabel()
        self._hint = QLabel()
        self._cursor = QLabel()
        self.statusBar().addWidget(self._info)
        self.statusBar().addWidget(self._hint, 1)
        self.statusBar().addPermanentWidget(self._cursor)
        self.statusBar().setSizeGripEnabled(False)

        self._build_actions()
        self._build_ribbon()
        self._show_current(keep_view=False)

    # ---- the current spectrum -----------------------------------------------------------

    @property
    def entry(self) -> Entry | None:
        if 0 <= self.current < len(self.document.entries):
            return self.document.entries[self.current]
        return None

    @property
    def dataset(self) -> Dataset | None:
        """The current data as loaded from the original files; never modified."""
        return self.entry.dataset if self.entry else None

    @property
    def spectrum(self) -> Dataset | None:
        """The current data processed with the current settings."""
        return _session(self.entry).spectrum if self.entry else None

    @property
    def params(self) -> ProcessingParams:
        return self.entry.params if self.entry else ProcessingParams()

    @property
    def integrals(self) -> IntegralSet:
        return self.entry.integrals if self.entry else IntegralSet()

    @property
    def multiplets(self) -> MultipletSet:
        return self.entry.multiplets if self.entry else MultipletSet()

    # ---- documents ----------------------------------------------------------------------

    def open_path(self, path: str | Path) -> bool:
        """Open a project file, or import data (file, folder or ZIP) into the document.

        Returns False (after telling the user) if nothing could be opened.
        """
        path = Path(path)
        if path.suffix.lower() == PROJECT_SUFFIX:
            return self.open_project(path)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            entries, errors = self.document.import_path(path)
        except LoadError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Could not open", str(exc))
            return False
        for entry in entries:
            self._process(entry)
        QApplication.restoreOverrideCursor()
        if errors:
            QMessageBox.warning(self, "Some data was skipped", "\n".join(errors))

        self._set_modified(True)
        self._rebuild_list(select=len(self.document.entries) - len(entries))
        return True

    def open_project(self, path: str | Path) -> bool:
        if not self._confirm_discard():
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            document = Document.open(path)
            for entry in document.entries:
                self._process(entry)
        except LoadError as exc:
            QMessageBox.warning(self, "Could not open", str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._replace_document(document)
        return True

    def new_document(self) -> None:
        if self._confirm_discard():
            self._replace_document(Document())

    def save(self) -> bool:
        if self.document.path is None:
            return self.save_as()
        return self._save_to(self.document.path)

    def save_as(self) -> bool:
        suggested = str(self.document.path or f"Untitled{PROJECT_SUFFIX}")
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", suggested, PROJECT_FILTER)
        if not path:
            return False
        if not path.lower().endswith(PROJECT_SUFFIX):
            path += PROJECT_SUFFIX
        return self._save_to(Path(path))

    def _save_to(self, path: Path) -> bool:
        try:
            self.document.save(path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save", f"{path}\n\n{exc}")
            return False
        self._set_modified(False)
        self._hint.setText(f"Saved {path.name}.")
        return True

    def export_spectrum(self, kind: str) -> bool:
        """Write the current, processed spectrum in an exchange format."""
        if self.spectrum is None:
            return False
        file_filter, suffix, writer = EXPORTERS[kind]
        path, _ = QFileDialog.getSaveFileName(self, f"Export as {kind}", "", file_filter)
        if not path:
            return False
        if not path.lower().endswith(suffix):
            path += suffix
        try:
            writer(self.spectrum, path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not export", f"{path}\n\n{exc}")
            return False
        self._hint.setText(f"Exported {Path(path).name}.")
        return True

    def select(self, index: int) -> None:
        """Show another spectrum of the document."""
        if index == self.current or not 0 <= index < len(self.document.entries):
            return
        self.current = index
        self.spectra_panel.set_current(index)
        self._show_current(keep_view=False)

    def remove_spectrum(self, index: int) -> None:
        if not 0 <= index < len(self.document.entries):
            return
        self.document.remove(index)
        self._set_modified(True)
        self._rebuild_list(select=min(index, len(self.document.entries) - 1))

    def _replace_document(self, document: Document) -> None:
        self.document.close()
        self.document = document
        self._set_modified(False)
        self._rebuild_list(select=0 if document.entries else -1)

    def _rebuild_list(self, *, select: int) -> None:
        self.current = select
        spectra = [_session(entry).spectrum for entry in self.document.entries]
        self.spectra_panel.set_spectra(spectra, select)
        self._show_current(keep_view=False)

    def _set_modified(self, modified: bool) -> None:
        self.modified = modified
        self._update_title()

    def _update_title(self) -> None:
        name = self.document.path.name if self.document.path else "Untitled"
        self.setWindowTitle(f"{name}{'*' if self.modified else ''} – nmr")

    def _confirm_discard(self) -> bool:
        """Ask what to do with unsaved changes. False means: do not go on."""
        if not self.modified:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save the changes to this project before closing it?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save()
        return answer == buttons.Discard

    # ---- processing ---------------------------------------------------------------------

    def set_params(
        self, params: ProcessingParams, *, record: bool = True, keep_view: bool = True
    ) -> None:
        """Apply new processing settings. With `record` the old ones go on the undo stack."""
        if self.entry is None or params == self.params:
            return
        if record:
            self._record_undo()
        self.entry.params = params
        self._set_modified(True)
        self._reprocess(keep_view=keep_view)

    def auto_phase(self, *, keep_view: bool = True) -> None:
        if self.entry is None or not np.iscomplexobj(self.dataset.data):
            return
        self.set_params(auto_phase(self.dataset, self.params), keep_view=keep_view)

    def set_integrals(self, integrals: IntegralSet, *, record: bool = True) -> None:
        if self.entry is None or integrals == self.integrals:
            return
        if record:
            self._record_undo()
        self.entry.integrals = integrals
        self._set_modified(True)
        self._refresh_integrals()
        self._update_enabled()

    def set_multiplets(self, multiplets: MultipletSet, *, record: bool = True) -> None:
        if self.entry is None or multiplets == self.multiplets:
            return
        if record:
            self._record_undo()
        self.entry.multiplets = multiplets
        self._set_modified(True)
        self._refresh_multiplets()
        self._update_enabled()

    def copy_report(self) -> None:
        """Put the multiplet report on the clipboard, as plain and as rich text."""
        results = self._analysed_multiplets()
        if not results:
            return
        data = QMimeData()
        data.setText(format_report(self.spectrum, results))
        data.setHtml(format_report(self.spectrum, results, html=True))
        QApplication.clipboard().setMimeData(data)
        self._hint.setText("Multiplet report copied to the clipboard.")

    def undo(self) -> None:
        self._step_history(back=True)

    def redo(self) -> None:
        self._step_history(back=False)

    def _step_history(self, *, back: bool) -> None:
        if self.entry is None:
            return
        session = _session(self.entry)
        source, target = (session.undo, session.redo) if back else (session.redo, session.undo)
        if source:
            target.append((self.params, self.integrals, self.multiplets))
            entry = self.entry
            entry.params, entry.integrals, entry.multiplets = source.pop()
            self._set_modified(True)
            self._reprocess(keep_view=True)

    def _record_undo(self) -> None:
        if self.entry is None:
            return
        session = _session(self.entry)
        session.undo.append((self.params, self.integrals, self.multiplets))
        session.redo.clear()
        self._update_enabled()

    def _process(self, entry: Entry) -> Dataset:
        """Recompute the spectrum of `entry` from its data and settings.

        The Fourier transform is redone only when a transform setting changed. Phase,
        baseline and referencing act on the spectrum, so dragging the phase does not
        repeat the transform on every mouse move.
        """
        session = _session(entry)
        transformed = entry.dataset
        if entry.dataset.domain == "time":
            params = entry.params
            key = (params.lb_hz, params.gb_hz, params.zero_fill_factor)
            if key != session.transform_key:
                session.transformed = fourier_transform(entry.dataset, params)
                session.transform_key = key
            transformed = session.transformed
        session.spectrum = process(transformed, entry.params)
        return session.spectrum

    def _reprocess(self, *, keep_view: bool) -> None:
        self.spectra_panel.update_spectrum(self.current, self._process(self.entry))
        self.panel.set_params(self.params)
        self.plot.set_pivot(self.params.pivot_ppm)
        self._refresh_plot(keep_view=keep_view)
        self._update_enabled()

    def _show_current(self, *, keep_view: bool) -> None:
        """Bring every part of the window in line with the current spectrum."""
        self.show_fid_action.blockSignals(True)
        self.show_fid_action.setChecked(False)
        self.show_fid_action.blockSignals(False)
        self._update_title()
        if self.entry is None:
            self.plot.clear_dataset()
            self.plot.set_pivot(None)
            self.plot.integrals.set(None, [])
            self.plot.multiplets.set([])
            self.panel.setEnabled(False)
            self.integrals_panel.set_integrals([], 0)
            self.multiplets_panel.set_multiplets([], "")
            self._info.setText("No data loaded")
            self._cursor.clear()
        else:
            is_fid = self.dataset.domain == "time"
            self.panel.set_capabilities(is_fid=is_fid, can_phase=np.iscomplexobj(self.dataset.data))
            self.panel.set_params(self.params)
            self.plot.set_pivot(self.params.pivot_ppm)
            self._refresh_plot(keep_view=keep_view)
        self._update_enabled()

    def _refresh_plot(self, *, keep_view: bool) -> None:
        shown = self.dataset if self.show_fid_action.isChecked() else self.spectrum
        self.plot.reserve_label_band = bool(self.multiplets.regions)
        self.plot.set_dataset(shown, keep_view=keep_view)
        self._info.setText(_describe(shown))
        self._cursor.clear()
        self._refresh_integrals()

    def _refresh_integrals(self) -> None:
        results = evaluate(self.spectrum, self.integrals)
        self.integrals_panel.set_integrals(results, self.integrals.ref_index)
        if self._showing_spectrum:
            self.plot.integrals.set(self.spectrum, results)
        else:
            self.plot.integrals.set(None, [])
        # The integrals set the scale for the nuclei counts of the multiplets.
        self._refresh_multiplets()

    def _analysed_multiplets(self) -> list:
        if self.spectrum is None:
            return []
        per_nucleus = None
        integrals = evaluate(self.spectrum, self.integrals)
        if integrals and integrals[0].value:
            per_nucleus = integrals[0].area / integrals[0].value
        return analyse(self.spectrum, self.multiplets, per_nucleus)

    def _refresh_multiplets(self) -> None:
        results = self._analysed_multiplets()
        report = format_report(self.spectrum, results) if results else ""
        self.multiplets_panel.set_multiplets(results, report)
        self.plot.reserve_label_band = bool(results)
        element = self.spectrum.nucleus.lstrip("0123456789") if self.spectrum else "H"
        self.plot.multiplets.set(results if self._showing_spectrum else [], element)

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
        if accepted and value != peak:
            # The integration regions move along with the axis, as one undo step.
            self._record_undo()
            self.entry.integrals = self.integrals.shifted(value - peak)
            self.entry.multiplets = self.multiplets.shifted(value - peak)
            self.set_params(shift_reference(self.params, value - peak), record=False)

    def _add_multiplet(self, a_ppm: float, b_ppm: float) -> None:
        if self._showing_spectrum:
            self.set_multiplets(self.multiplets.add(a_ppm, b_ppm))
            self.multiplets_dock.raise_()

    def _add_integral(self, a_ppm: float, b_ppm: float) -> None:
        if self._showing_spectrum:
            self.set_integrals(self.integrals.add(a_ppm, b_ppm))

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
        self.new_action = self._action("&New", self.new_document, std.New)
        self.open_file_action = self._action(
            "&Open…", self._choose_file, std.Open, tip="Open a project or import data"
        )
        self.open_folder_action = self._action(
            "Import &Folder…", self._choose_folder, "Ctrl+Shift+O", tip="Import a data folder"
        )
        self.save_action = self._action("&Save", self.save, std.Save)
        self.save_as_action = self._action("Save &As…", self.save_as, "Ctrl+Shift+S")
        self.export_actions = [
            self._action(f"{kind}…", lambda _=False, k=kind: self.export_spectrum(k))
            for kind in EXPORTERS
        ]
        self.quit_action = self._action("&Quit", self.close, "Ctrl+Q")

        self.undo_action = self._action("&Undo", self.undo, std.Undo)
        self.redo_action = self._action("&Redo", self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"])
        self.copy_action = self._action("&Copy as Image", self.copy_image, std.Copy)
        self.remove_action = self._action(
            "&Remove Spectrum", lambda: self.remove_spectrum(self.current)
        )
        self.previous_action = self._action(
            "&Previous Spectrum", lambda: self.select(self.current - 1), "PgUp"
        )
        self.next_action = self._action(
            "&Next Spectrum", lambda: self.select(self.current + 1), "PgDown"
        )

        tools = [
            (Tool.SELECT, "&Select", "Esc", "Select tool: drag to move the spectrum"),
            (Tool.ZOOM, "&Zoom", "Z", "Zoom in: drag to select a region"),
            (Tool.PAN, "&Pan", "P", "Pan the spectrum"),
            (Tool.CROSSHAIR, "&Crosshair", "C", "Crosshair cursor for measuring distances"),
            (Tool.PHASE, "&Manual Phase", "Shift+P", "Manual phase correction"),
            (Tool.REFERENCE, "&Reference", "L", "Set the chemical shift reference"),
            (Tool.INTEGRATE, "&Integrate", "I", "Manual integration: drag across a signal"),
            (Tool.MULTIPLET, "&Multiplets", "J", "Multiplet analysis: drag across a signal"),
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
        self.clear_integrals_action = self._action(
            "&Delete All Integrals", lambda: self.set_integrals(IntegralSet())
        )
        self.clear_multiplets_action = self._action(
            "Delete All &Multiplets", lambda: self.set_multiplets(MultipletSet())
        )
        self.copy_report_action = self._action(
            "Copy Multiplet &Report", self.copy_report, "Ctrl+Shift+C"
        )
        self.shortcuts_action = self._action("&Keyboard Shortcuts", self._show_shortcuts, "F1")
        self.about_action = self._action("&About nmr", self._show_about)

    def _build_ribbon(self) -> None:
        """Tabs with icon buttons, in place of a menu bar and tool bar."""

        def use(action: QAction, icon: str, label: str) -> QAction:
            action.setIcon(icons.icon(icon))
            action.setIconText(label)
            return action

        tool = self.tool_actions
        new = use(self.new_action, "new", "New")
        open_ = use(self.open_file_action, "open", "Open")
        import_ = use(self.open_folder_action, "import", "Import folder")
        save = use(self.save_action, "save", "Save")
        save_as = use(self.save_as_action, "save-as", "Save as")
        exports = [
            use(action, "export", f"Export {kind}")
            for action, kind in zip(self.export_actions, EXPORTERS, strict=True)
        ]
        quit_ = use(self.quit_action, "quit", "Quit")
        undo = use(self.undo_action, "undo", "Undo")
        redo = use(self.redo_action, "redo", "Redo")
        copy = use(self.copy_action, "copy", "Copy image")
        remove = use(self.remove_action, "remove", "Remove")
        select = use(tool[Tool.SELECT], "select", "Select")
        zoom = use(tool[Tool.ZOOM], "zoom", "Zoom")
        zoom_out = use(self.zoom_out_action, "zoom-out", "Zoom out")
        pan = use(tool[Tool.PAN], "pan", "Pan")
        crosshair = use(tool[Tool.CROSSHAIR], "crosshair", "Crosshair")
        full = use(self.full_action, "full", "Full")
        fit = use(self.fit_action, "fit-height", "Fit height")
        bigger = use(self.bigger_action, "intensity-up", "Increase")
        smaller = use(self.smaller_action, "intensity-down", "Decrease")
        previous = use(self.previous_action, "previous", "Previous")
        next_ = use(self.next_action, "next", "Next")
        fid = use(self.show_fid_action, "fid", "FID")
        auto_phase_ = use(self.auto_phase_action, "auto-phase", "Auto phase")
        phase = use(tool[Tool.PHASE], "phase", "Manual phase")
        reference = use(tool[Tool.REFERENCE], "reference", "Reference")
        integrate = use(tool[Tool.INTEGRATE], "integrate", "Integrate")
        clear = use(self.clear_integrals_action, "clear-integrals", "Delete all")
        multiplet = use(tool[Tool.MULTIPLET], "multiplet", "Multiplets")
        clear_multiplets = use(self.clear_multiplets_action, "clear-multiplets", "Delete all")
        report = use(self.copy_report_action, "report", "Copy report")
        shortcuts = use(self.shortcuts_action, "shortcuts", "Shortcuts")
        about = use(self.about_action, "about", "About")
        panels = [
            use(self.spectra_dock.toggleViewAction(), "panel-left", "Spectra"),
            use(self.dock.toggleViewAction(), "panel-right", "Processing"),
            use(self.integrals_dock.toggleViewAction(), "panel-table", "Integrals"),
            use(self.multiplets_dock.toggleViewAction(), "panel-table", "Multiplets"),
        ]
        names = ("spectra", "processing", "integrals", "multiplets")
        for action, name in zip(panels, names, strict=True):
            action.setToolTip(f"Show or hide the {name} panel")

        pages = {
            "&File": [[new, open_, import_], [save, save_as], exports, [quit_]],
            "&Home": [
                [open_, save],
                [undo, redo, copy],
                [select, zoom, pan, crosshair],
                [full, fit],
                [auto_phase_, reference],
                [integrate, multiplet, report],
            ],
            "&View": [
                [select, zoom, zoom_out, pan, crosshair],
                [full, fit, bigger, smaller],
                [previous, next_, remove],
                [fid],
                panels,
            ],
            "&Processing": [[auto_phase_, phase], [reference], [fid]],
            "&Analysis": [[integrate, clear], [multiplet, clear_multiplets, report]],
            "H&elp": [[shortcuts, about]],
        }
        self.ribbon = Ribbon()
        for title, groups in pages.items():
            page = self.ribbon.add_page(title)
            for group in groups:
                page.add_group(group)
        self.ribbon.show_page("Home")
        self.setMenuWidget(self.ribbon)

    def _update_enabled(self) -> None:
        loaded = self.entry is not None
        is_fid = loaded and self.dataset.domain == "time"
        complex_data = loaded and np.iscomplexobj(self.dataset.data)
        for action in (
            self.copy_action,
            self.remove_action,
            self.zoom_out_action,
            self.full_action,
            self.fit_action,
            self.bigger_action,
            self.smaller_action,
            self.tool_actions[Tool.REFERENCE],
            self.tool_actions[Tool.INTEGRATE],
            self.tool_actions[Tool.MULTIPLET],
            *self.export_actions,
        ):
            action.setEnabled(loaded)
        count = len(self.document.entries)
        self.save_action.setEnabled(count > 0)
        self.save_as_action.setEnabled(count > 0)
        self.previous_action.setEnabled(self.current > 0)
        self.next_action.setEnabled(0 <= self.current < count - 1)
        self.clear_integrals_action.setEnabled(bool(self.integrals.ranges))
        self.clear_multiplets_action.setEnabled(bool(self.multiplets.regions))
        self.copy_report_action.setEnabled(bool(self.multiplets.regions))
        self.show_fid_action.setEnabled(is_fid)
        self.auto_phase_action.setEnabled(complex_data)
        self.tool_actions[Tool.PHASE].setEnabled(complex_data)
        session = _session(self.entry) if loaded else _Session()
        self.undo_action.setEnabled(bool(session.undo))
        self.redo_action.setEnabled(bool(session.redo))

    def _add_dock(
        self, title: str, widget, area=Qt.DockWidgetArea.RightDockWidgetArea
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(area, dock)
        return dock

    # ---- dialogs and events -------------------------------------------------------------

    def _choose_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open", "", OPEN_FILTER)
        for path in paths:
            self.open_path(path)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Import Folder")
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            self.document.close()
            event.accept()
        else:
            event.ignore()

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
