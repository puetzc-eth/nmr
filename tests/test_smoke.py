import subprocess
import sys


def test_core_does_not_import_qt():
    code = "import sys, nmr.core; sys.exit(any(m.startswith('PySide6') for m in sys.modules))"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_main_window_opens(qtbot):
    from nmr.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    assert window.plot.getViewBox().xInverted()
