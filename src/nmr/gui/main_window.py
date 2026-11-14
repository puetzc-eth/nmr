"""Main application window."""

import pyqtgraph as pg
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox

from nmr import __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("nmr")
        self.resize(1200, 700)

        self.plot = pg.PlotWidget(background="w")
        self.plot.setLabel("bottom", "δ", units="ppm")
        self.plot.hideAxis("left")
        # NMR convention: chemical shift increases to the left.
        self.plot.getViewBox().invertX(True)
        self.setCentralWidget(self.plot)

        self._build_menus()
        self.statusBar().showMessage("Kein Spektrum geladen")

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Datei")
        quit_action = QAction("&Beenden", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Hilfe")
        about_action = QAction("&Über nmr", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        QMessageBox.about(self, "Über nmr", f"nmr {__version__}\nOpen-Source-NMR-Auswertung")
