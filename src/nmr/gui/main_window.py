"""Main application window."""

from pathlib import Path

from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from nmr import __version__
from nmr.core.dataset import Dataset
from nmr.core.io import LoadError, load
from nmr.gui.spectrum_view import SpectrumView, format_nucleus

FILE_FILTER = "NMR-Daten (*.dx *.jdx *.jcamp fid 1r);;Alle Dateien (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("nmr")
        self.resize(1200, 700)
        self.setAcceptDrops(True)

        self.dataset: Dataset | None = None
        self.plot = SpectrumView()
        self.setCentralWidget(self.plot)

        self._build_menus()
        self.statusBar().showMessage("Kein Spektrum geladen – Datei oder Bruker-Ordner öffnen")

    def open_path(self, path: str | Path) -> bool:
        """Load a file or folder and show it. Returns False (after telling the user) on failure."""
        try:
            dataset = load(path)
        except LoadError as exc:
            QMessageBox.warning(self, "Öffnen fehlgeschlagen", str(exc))
            return False

        self.dataset = dataset
        self.plot.set_dataset(dataset)
        self.setWindowTitle(f"{dataset.title} – nmr" if dataset.title else "nmr")
        self.statusBar().showMessage(_describe(dataset))
        return True

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Datei")

        open_file = QAction("Datei &öffnen…", self)
        open_file.setShortcut(QKeySequence.StandardKey.Open)
        open_file.triggered.connect(self._choose_file)
        file_menu.addAction(open_file)

        open_folder = QAction("&Bruker-Ordner öffnen…", self)
        open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_folder.triggered.connect(self._choose_folder)
        file_menu.addAction(open_folder)

        file_menu.addSeparator()
        quit_action = QAction("&Beenden", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Hilfe")
        about_action = QAction("&Über nmr", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Datei öffnen", "", FILE_FILTER)
        if path:
            self.open_path(path)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Bruker-Ordner öffnen")
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_path(urls[0].toLocalFile())

    def _show_about(self) -> None:
        QMessageBox.about(self, "Über nmr", f"nmr {__version__}\nOpen-Source-NMR-Auswertung")


def _describe(dataset: Dataset) -> str:
    parts = [
        format_nucleus(dataset.nucleus),
        f"{dataset.obs_freq_mhz:.2f} MHz",
        "FID" if dataset.domain == "time" else "Spektrum",
        f"{dataset.size} Punkte",
        dataset.solvent,
    ]
    return "  ·  ".join(p for p in parts if p)
