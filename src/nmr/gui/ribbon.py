"""A ribbon: a row of tabs with, below it, a strip of icon buttons for the chosen tab.

It takes the place of the classic menu bar and tool bar. Buttons are bound to
QActions, so text, icon, tooltip, shortcut, enabled and checked state all come from
the action and stay in sync with it.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

ICON_SIZE = QSize(20, 20)


class RibbonPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 4, 10, 5)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self.buttons: list[QToolButton] = []

    def add_group(self, actions: list[QAction]) -> None:
        """Add buttons for `actions`, set apart from the previous group by a thin line."""
        position = self._layout.count() - 1  # in front of the stretch
        if self.buttons:
            line = QFrame()
            line.setObjectName("ribbonSeparator")
            line.setFixedWidth(1)
            self._layout.insertWidget(position, line)
            position += 1
        for action in actions:
            button = QToolButton()
            button.setObjectName("ribbonButton")
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIconSize(ICON_SIZE)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumWidth(58)
            self._layout.insertWidget(position, button)
            position += 1
            self.buttons.append(button)


class Ribbon(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ribbon")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.tabs = QTabBar()
        self.tabs.setObjectName("ribbonTabs")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pages = QStackedWidget()
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)

        strip = QHBoxLayout()
        strip.setContentsMargins(8, 0, 8, 0)
        strip.addWidget(self.tabs)
        strip.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(strip)
        layout.addWidget(self.pages)

    def add_page(self, title: str) -> RibbonPage:
        """Add a tab. An ampersand in the title marks its Alt+letter shortcut."""
        page = RibbonPage()
        self.pages.addWidget(page)
        self.tabs.addTab(title)
        return page

    def show_page(self, title: str) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index).replace("&", "") == title:
                self.tabs.setCurrentIndex(index)

    def page_titles(self) -> list[str]:
        return [self.tabs.tabText(i).replace("&", "") for i in range(self.tabs.count())]
