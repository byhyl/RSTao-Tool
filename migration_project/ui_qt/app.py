"""Application bootstrap for the Qt preview UI."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from common.app_icon import resolve_app_icon_path
from common.version import APP_NAME
from .main_window import MainWindow
from .theme import DEFAULT_THEME, load_stylesheet


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} Studio Preview")
    app.setOrganizationName("RSTao")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)

    icon_path = resolve_app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyleSheet(load_stylesheet(DEFAULT_THEME))

    window = MainWindow()
    window.show()
    return app.exec()
