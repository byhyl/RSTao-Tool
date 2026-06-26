"""Runtime log dock for the Qt preview workbench."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class LogDock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.output)

    def append(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.output.appendPlainText(f"[{stamp}] {message}")
