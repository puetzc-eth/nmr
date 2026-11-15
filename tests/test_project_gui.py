"""The window as a multi-spectrum document: sidebar, saving, opening."""

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

DATA = Path(__file__).parent / "data"


@pytest.fixture
def window(qtbot):
    from nmr.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def two_spectra(window, jcamp_dir):
    assert window.open_path(DATA / "bruker" / "ibuprofen-13c-processed.zip")
    assert window.open_path(jcamp_dir / "aspirin-1h.fid.dx")
    return window


def test_empty_document(window):
    assert window.windowTitle() == "Untitled – nmr"
    assert window.spectra_panel.list.count() == 0
    assert not window.save_action.isEnabled()
    assert not window.remove_action.isEnabled()
    assert not window.modified


def test_opening_adds_spectra_to_the_sidebar(two_spectra):
    window = two_spectra
    spectra = window.spectra_panel.list

    assert spectra.count() == 2
    assert spectra.item(0).text().startswith("¹³C")
    assert spectra.item(1).text() == "¹H  1H BBI"
    assert not spectra.item(0).icon().isNull()
    # The spectrum opened last is shown.
    assert window.current == 1 and spectra.currentRow() == 1
    assert window.dataset.nucleus == "1H"
    assert window.modified and window.windowTitle() == "Untitled* – nmr"
    assert window.save_action.isEnabled()


def test_switching_keeps_each_spectrum_separate(two_spectra):
    window = two_spectra
    window.panel.lb.setValue(2.0)
    window.plot.region_selected.emit(2.5, 2.2)

    window.spectra_panel.list.setCurrentRow(0)  # what a click in the sidebar does

    assert window.current == 0
    assert window.dataset.nucleus == "13C"
    assert window.panel.lb.value() == 1.0
    assert window.integrals_panel.table.rowCount() == 0
    assert len(window.plot.integrals) == 0
    assert not window.undo_action.isEnabled()  # undo history is per spectrum
    low, high = window.plot.vb.viewRange()[0]
    assert low < 0 and high > 200  # the view was reset to the carbon range

    window.next_action.trigger()
    assert window.current == 1
    assert window.panel.lb.value() == 2.0
    assert window.integrals_panel.table.rowCount() == 1
    assert window.undo_action.isEnabled()
    assert not window.next_action.isEnabled()
    window.previous_action.trigger()
    assert window.current == 0


def test_sidebar_preview_follows_processing(two_spectra):
    window = two_spectra
    item = window.spectra_panel.list.item(1)
    before = item.icon().pixmap(200, 70).toImage()

    window.panel.ph0.setValue(window.panel.ph0.value() + 90.0)

    assert item.icon().pixmap(200, 70).toImage() != before


def test_remove_spectrum(two_spectra):
    window = two_spectra
    window.remove_action.trigger()  # removes the current one (aspirin)

    assert window.spectra_panel.list.count() == 1
    assert window.current == 0 and window.dataset.nucleus == "13C"

    window.spectra_panel.remove_requested.emit(0)
    assert window.entry is None
    assert window._info.text() == "No data loaded"
    assert not window.panel.isEnabled()
    assert len(window.plot.curve.getOriginalDataset()[0] or []) == 0


def test_save_and_reopen(two_spectra, tmp_path, monkeypatch, qtbot):
    from nmr.gui.main_window import MainWindow

    window = two_spectra
    window.panel.lb.setValue(2.0)
    window.plot.region_selected.emit(2.5, 2.2)
    window.plot.region_selected.emit(7.2, 7.0)
    window.integrals_panel.table.item(1, 2).setText("3")
    shown = window.plot.curve.getOriginalDataset()[1].copy()
    values = [window.integrals_panel.table.item(r, 2).text() for r in range(2)]

    # Without a file name, Save asks for one; the suffix is added if it is missing.
    target = tmp_path / "ibuprofen study"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_action.trigger()

    saved = tmp_path / "ibuprofen study.nmrx"
    assert saved.is_file()
    assert not window.modified
    assert window.windowTitle() == "ibuprofen study.nmrx – nmr"

    other = MainWindow()
    qtbot.addWidget(other)
    assert other.open_path(saved)

    assert other.spectra_panel.list.count() == 2
    assert not other.modified
    assert other.windowTitle() == "ibuprofen study.nmrx – nmr"
    assert other.current == 0 and other.dataset.nucleus == "13C"
    other.select(1)
    assert other.panel.lb.value() == 2.0
    np.testing.assert_allclose(other.plot.curve.getOriginalDataset()[1], shown)
    assert [other.integrals_panel.table.item(r, 2).text() for r in range(2)] == values

    # Saving again goes to the same file without asking.
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: pytest.fail("asked"))
    other.panel.lb.setValue(0.5)
    assert other.windowTitle().startswith("ibuprofen study.nmrx*")
    other.save_action.trigger()
    assert not other.modified


def test_cancelled_save_dialog_keeps_the_document_modified(two_spectra, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert not two_spectra.save()
    assert two_spectra.modified and two_spectra.document.path is None


@pytest.mark.parametrize(
    ("answer", "kept"),
    [(QMessageBox.StandardButton.Cancel, True), (QMessageBox.StandardButton.Discard, False)],
)
def test_new_asks_about_unsaved_changes(two_spectra, monkeypatch, answer, kept):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a: asked.append(a[2]) or answer)

    two_spectra.new_action.trigger()

    assert len(asked) == 1
    assert (len(two_spectra.document.entries) == 2) is kept
    if not kept:
        assert not two_spectra.modified
        assert two_spectra.spectra_panel.list.count() == 0


def test_closing_with_unsaved_changes_can_be_cancelled(two_spectra, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    assert not two_spectra.close()
    assert two_spectra.isVisible()

    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    assert two_spectra.close()


def test_unmodified_document_closes_without_asking(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("asked"))
    assert window.close()


def test_broken_project_file_leaves_the_document_alone(two_spectra, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    broken = tmp_path / "broken.nmrx"
    broken.write_text("nope")

    assert not two_spectra.open_path(broken)
    assert "not a readable project file" in shown[0]
    assert len(two_spectra.document.entries) == 2


def test_import_jeol_and_export_jcamp(window, tmp_path, monkeypatch):
    from nmr.core.io import load

    assert not window.export_actions[0].isEnabled()
    assert window.open_path(DATA / "jeol" / "rutin-1h.jdf")
    assert window.spectra_panel.list.item(0).text() == "¹H  Rutin_RUTI01_3080u200u"

    target = tmp_path / "rutin"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    jcamp_action, csv_action = window.export_actions
    jcamp_action.trigger()
    csv_action.trigger()

    exported = load(tmp_path / "rutin.jdx")
    np.testing.assert_allclose(exported.ppm_axis, window.spectrum.ppm_axis, atol=1e-9)
    assert (tmp_path / "rutin.csv").read_text().startswith("ppm,intensity")
    # Exporting does not count as saving the project.
    assert window.modified
