"""Application start-up."""

import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from nmr.gui.main_window import MainWindow
from nmr.gui.theme import apply_theme


def run(argv: list[str]) -> int:
    """Start the app. An optional first argument is a file or folder to open."""
    app = QApplication(argv)
    app.setApplicationName("nmr")
    apply_theme(app)
    pg.setConfigOptions(antialias=True)
    window = MainWindow()
    window.show()
    args = app.arguments()[1:]
    if args:
        # Open after the window is on screen so an error dialog has a visible parent.
        QTimer.singleShot(0, lambda: window.open_path(args[0]))
    return app.exec()
