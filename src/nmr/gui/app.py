"""Application start-up."""

from PySide6.QtWidgets import QApplication

from nmr.gui.main_window import MainWindow


def run(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("nmr")
    window = MainWindow()
    window.show()
    return app.exec()
