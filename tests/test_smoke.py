import subprocess
import sys

import numpy as np


def test_core_does_not_import_qt():
    code = (
        "import sys, nmr.core.io;"
        "sys.exit(any(m.startswith(('PySide6', 'pyqtgraph')) for m in sys.modules))"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_main_window_opens(qtbot):
    from nmr.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    assert window.plot.getViewBox().xInverted()


def test_open_fid_and_spectrum(qtbot, jcamp_dir):
    from nmr.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.open_path(jcamp_dir / "aspirin-1h.fid.dx")
    x, y = window.plot.curve.getOriginalDataset()
    assert len(x) == len(y) == 8192
    assert not window.plot.getViewBox().xInverted()
    assert "FID" in window.statusBar().currentMessage()

    assert window.open_path(jcamp_dir / "aspirin-1h.dx")
    x, y = window.plot.curve.getOriginalDataset()
    assert len(x) == 32768
    assert np.isrealobj(y)
    # What is actually drawn after clipping and downsampling must still span the spectrum.
    shown_x, _ = window.plot.curve.getData()
    assert shown_x.min() < 0 and shown_x.max() > 15
    assert window.plot.getViewBox().xInverted()
    assert "Spektrum" in window.statusBar().currentMessage()


def test_open_failure_shows_message(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from nmr.gui.main_window import MainWindow

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: shown.append(args[2]))
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.open_path(tmp_path / "missing.dx")
    assert shown and window.dataset is None
