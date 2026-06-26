"""Resource import dialog with preview via input_inspector."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..i18n import tr


class ResourceImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.import_resource.title"))
        self.setMinimumSize(600, 420)
        self._result: dict | None = None

        layout = QVBoxLayout(self)

        # File selection
        file_group = QGroupBox(tr("dialog.import_resource.file"))
        file_layout = QHBoxLayout(file_group)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self.path_edit)
        file_layout.addWidget(browse_btn)

        # Preview
        preview_group = QGroupBox(tr("dialog.import_resource.preview"))
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)
        preview_layout.addWidget(self.preview_text)

        # Status
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        layout.addWidget(file_group)
        layout.addWidget(preview_group)
        layout.addWidget(self.status_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.ok_btn:
            self.ok_btn.setEnabled(False)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dialog.import_resource.title"), "",
            tr("filter.resources")
        )
        if not path:
            return
        self.path_edit.setText(path)
        self._inspect(path)

    def _inspect(self, path: str) -> None:
        try:
            from core.input_inspector import inspect_file
            result = inspect_file(path)
            self._result = {
                "path": path,
                "can_import": result.can_import,
                "kind": result.kind,
                "title": result.title,
                "detail": result.detail_text(),
            }
            self.preview_text.setPlainText(result.detail_text())
            if result.can_import:
                self.status_label.setText(
                    tr("dialog.import_resource.ready", kind=result.kind)
                )
                self.status_label.setStyleSheet("color: green;")
                if self.ok_btn:
                    self.ok_btn.setEnabled(True)
            else:
                self.status_label.setText(
                    tr("dialog.import_resource.cannot_import", reason=result.message)
                )
                self.status_label.setStyleSheet("color: red;")
                if self.ok_btn:
                    self.ok_btn.setEnabled(False)
        except Exception as exc:
            self.preview_text.setPlainText(str(exc))
            self.status_label.setText(tr("dialog.import_resource.error"))
            self.status_label.setStyleSheet("color: red;")

    def _accept(self) -> None:
        if self._result and self._result.get("can_import"):
            self.accept()

    def get_result(self) -> dict | None:
        return self._result
