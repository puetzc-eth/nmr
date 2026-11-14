import subprocess
import sys
from dataclasses import replace

import numpy as np
import pytest


def test_core_does_not_import_qt():
    code = (
        "import sys, nmr.core.io, nmr.core.processing;"
        "sys.exit(any(m.startswith(('PySide6', 'pyqtgraph')) for m in sys.modules))"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


@pytest.fixture
def window(qtbot):
    from nmr.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def aspirin(window, jcamp_dir):
    assert window.open_path(jcamp_dir / "aspirin-1h.fid.dx")
    return window


def curve(window):
    return window.plot.curve.getOriginalDataset()


def test_empty_window(window):
    assert window.isVisible()
    assert window.plot.vb.xInverted()
    assert not window.panel.isEnabled()
    assert not window.full_action.isEnabled()
    assert not window.undo_action.isEnabled()
    assert window._info.text() == "No data loaded"


def test_opening_a_fid_shows_the_phased_spectrum(aspirin):
    window = aspirin
    x, y = curve(window)

    assert len(x) == len(y) == 16384
    assert np.isrealobj(y)
    assert window.plot.vb.xInverted()
    assert "Spectrum" in window._info.text()
    # Automatically phased: essentially no negative intensity.
    assert y.min() > -0.02 * y.max()
    assert window.panel.transform_group.isEnabled()
    assert window.panel.lb.value() == 0.3
    assert window.panel.ph0.value() == pytest.approx(window.params.ph0_deg, abs=0.01)
    assert not window.undo_action.isEnabled()
    # What is actually drawn after clipping and downsampling must still span the spectrum.
    shown_x, _ = window.plot.curve.getData()
    assert shown_x.min() < 0 and shown_x.max() > 15


def test_toggle_between_fid_and_spectrum(aspirin):
    window = aspirin

    window.show_fid_action.trigger()
    assert len(curve(window)[0]) == 8192
    assert not window.plot.vb.xInverted()
    assert "FID" in window._info.text()

    window.show_fid_action.trigger()
    assert len(curve(window)[0]) == 16384


def test_panel_edits_reprocess_and_keep_zoom(aspirin):
    window = aspirin
    window.plot.vb.setRange(xRange=(2.0, 3.0), padding=0)
    _, before = curve(window)

    window.panel.ph0.setValue(window.panel.ph0.value() + 90.0)
    assert not np.allclose(before, curve(window)[1])
    assert window.plot.vb.viewRange()[0] == pytest.approx([2.0, 3.0])

    window.panel.zero_fill.setCurrentIndex(window.panel.zero_fill.findData(4))
    assert len(curve(window)[0]) == 32768

    window.panel.baseline.setChecked(True)
    assert window.params.baseline_order == 3

    window.panel.auto_phase.click()
    _, rephased = curve(window)
    assert rephased.min() > -0.02 * rephased.max()


def test_undo_and_redo(aspirin):
    window = aspirin
    original = window.params

    window.panel.lb.setValue(2.0)
    window.panel.ph0.setValue(10.0)
    assert window.undo_action.isEnabled()

    window.undo_action.trigger()
    assert window.params.lb_hz == 2.0
    assert window.params.ph0_deg == pytest.approx(original.ph0_deg)
    window.undo_action.trigger()
    assert window.params == original
    assert not window.undo_action.isEnabled()

    window.redo_action.trigger()
    assert window.params.lb_hz == 2.0
    assert window.panel.lb.value() == 2.0


def test_opening_a_spectrum_leaves_it_unchanged(window, jcamp_dir):
    from nmr.core.io import load
    from nmr.gui.spectrum_view import Tool

    assert window.open_path(jcamp_dir / "aspirin-1h.dx")

    np.testing.assert_array_equal(
        curve(window)[1][::-1], load(jcamp_dir / "aspirin-1h.dx").data.real
    )
    assert not window.panel.transform_group.isEnabled()
    assert window.panel.phase_group.isEnabled()
    assert not window.show_fid_action.isEnabled()

    # Real-only data cannot be phased.
    assert window.open_path(jcamp_dir / "jeol-1h.dx")
    assert not window.panel.phase_group.isEnabled()
    assert not window.tool_actions[Tool.PHASE].isEnabled()
    assert not window.auto_phase_action.isEnabled()
    assert window.panel.baseline_group.isEnabled()


def test_open_failure_shows_message(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: shown.append(args[2]))

    assert not window.open_path(tmp_path / "missing.dx")
    assert shown == [f"Path not found: {tmp_path / 'missing.dx'}"]
    assert window.dataset is None


def test_shortcuts_match_mnova(window):
    """The single-key shortcuts NMR users know from Mnova."""
    from nmr.gui.spectrum_view import Tool

    def keys(action):
        return [s.toString() for s in action.shortcuts()]

    assert keys(window.tool_actions[Tool.ZOOM]) == ["Z"]
    assert keys(window.tool_actions[Tool.PAN]) == ["P"]
    assert keys(window.tool_actions[Tool.CROSSHAIR]) == ["C"]
    assert keys(window.tool_actions[Tool.PHASE]) == ["Shift+P"]
    assert keys(window.tool_actions[Tool.REFERENCE]) == ["L"]
    assert keys(window.tool_actions[Tool.SELECT]) == ["Esc"]
    assert keys(window.zoom_out_action) == ["Shift+Z"]
    assert keys(window.full_action) == ["F"]
    assert keys(window.fit_action) == ["H"]
    assert keys(window.open_file_action) == ["Ctrl+O"]
    assert "Ctrl+Z" in keys(window.undo_action)
    assert "Ctrl+C" in keys(window.copy_action)

    # No key may be bound twice.
    bound = [k for action in window.actions() for k in keys(action)]
    assert len(bound) == len(set(bound))


def test_keyboard_selects_tools_and_cycles_modes(aspirin, qtbot):
    from PySide6.QtCore import Qt

    from nmr.gui.spectrum_view import Tool

    window = aspirin
    window.plot.setFocus()

    qtbot.keyClick(window.plot, Qt.Key.Key_Z)
    assert window.plot.tool is Tool.ZOOM
    assert window.plot.zoom_mode == "horizontal"
    assert window.tool_actions[Tool.ZOOM].isChecked()
    assert "horizontal" in window._hint.text()

    qtbot.keyClick(window.plot, Qt.Key.Key_Z)
    assert window.plot.zoom_mode == "vertical"
    qtbot.keyClick(window.plot, Qt.Key.Key_Z)
    assert window.plot.zoom_mode == "box"

    qtbot.keyClick(window.plot, Qt.Key.Key_P)
    assert window.plot.tool is Tool.PAN
    qtbot.keyClick(window.plot, Qt.Key.Key_P, Qt.KeyboardModifier.ShiftModifier)
    assert window.plot.tool is Tool.PHASE
    qtbot.keyClick(window.plot, Qt.Key.Key_Escape)
    assert window.plot.tool is Tool.SELECT


def test_view_commands(aspirin):
    window = aspirin
    view = window.plot
    full_x = view.vb.viewRange()[0]

    view.vb.setRange(xRange=(6.5, 8.5), yRange=(0, 1), padding=0)
    window.fit_action.trigger()
    x, y = curve(window)
    tallest = y[(x > 6.5) & (x < 8.5)].max()
    low, high = view.vb.viewRange()[1]
    assert low < 0 < tallest < high < 1.2 * tallest
    assert view.vb.viewRange()[0] == pytest.approx([6.5, 8.5])

    window.bigger_action.trigger()
    assert view.vb.viewRange()[1][1] < high
    # The zero line does not move when the intensity is scaled.
    new_low, new_high = view.vb.viewRange()[1]
    assert new_low / new_high == pytest.approx(low / high)

    window.zoom_out_action.trigger()
    assert view.vb.viewRange()[0] == pytest.approx([5.5, 9.5])

    window.full_action.trigger()
    assert view.vb.viewRange()[0] == pytest.approx(full_x)


def test_manual_phase_drag_and_pivot(aspirin):
    window = aspirin
    before = window.params

    window.plot.phase_drag_started.emit()
    window.plot.phase_dragged.emit(12.0, 0.0)
    window.plot.phase_dragged.emit(0.0, 30.0)
    assert window.params.ph0_deg == pytest.approx(before.ph0_deg + 12.0)
    assert window.params.ph1_deg == pytest.approx(before.ph1_deg + 30.0)

    # One drag is one undo step.
    window.undo_action.trigger()
    assert window.params == before

    # Moving the pivot leaves the spectrum as it is.
    window.set_params(replace(before, ph1_deg=before.ph1_deg + 90.0))
    _, shown = curve(window)
    window.plot.pivot_picked.emit(7.0)
    assert window.params.pivot_ppm == 7.0
    np.testing.assert_allclose(curve(window)[1], shown, atol=1e-6 * np.abs(shown).max())


def test_reference_by_clicking_a_signal(aspirin, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = aspirin
    x, y = curve(window)
    peak = x[np.argmax(y)]
    asked = []

    def fake_get_double(parent, title, label, value, *args):
        asked.append(label)
        return 2.36, True

    monkeypatch.setattr(QInputDialog, "getDouble", fake_get_double)
    # Clicking slightly beside the signal snaps to its top.
    window.plot.reference_picked.emit(peak + 0.01)

    assert f"{peak:.4f}" in asked[0]
    x, y = curve(window)
    assert x[np.argmax(y)] == pytest.approx(2.36, abs=1e-6)
    assert window.params.pivot_ppm == pytest.approx(2.36, abs=1e-3)

    window.undo_action.trigger()
    assert curve(window)[0][np.argmax(curve(window)[1])] == pytest.approx(peak)


def test_crosshair_reports_position_and_distance(aspirin):
    window = aspirin
    window.plot.cursor_moved.emit(7.26)
    assert window._cursor.text() == "7.2600 ppm   2178.94 Hz"

    window.plot.distance_measured.emit(7.26, 7.24)
    assert window._hint.text() == "Δ = 0.0200 ppm = 6.00 Hz"


def test_copy_puts_an_image_on_the_clipboard(aspirin):
    from PySide6.QtWidgets import QApplication

    aspirin.copy_action.trigger()
    assert not QApplication.clipboard().pixmap().isNull()


def test_shortcuts_dialog_lists_every_bound_key(window):
    from nmr.gui.shortcuts_dialog import SHORTCUTS, ShortcutsDialog

    dialog = ShortcutsDialog(window)
    assert dialog.table.rowCount() == sum(len(entries) + 1 for _, entries in SHORTCUTS)

    listed = " ".join(keys for _, entries in SHORTCUTS for keys, _ in entries)
    for action in window.actions():
        for shortcut in action.shortcuts():
            key = shortcut.toString()
            if key in ("=", "-", "+"):
                continue
            assert key in listed, f"{key} ({action.text()}) is missing from the shortcut list"
