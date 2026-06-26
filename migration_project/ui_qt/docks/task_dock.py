"""Task history dock showing TaskHistory from ProjectService."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from ..i18n import tr


class TaskDock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: dict | None = None

        self.tasks = QListWidget()

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(self.refresh)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_history)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(btn_row)
        layout.addWidget(self.tasks)
        self.retranslate_ui()

    def set_project(self, project: dict | None) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        self.tasks.clear()
        window = self.window()
        project = None
        if hasattr(window, "_ctx"):
            project = window._ctx.project_service.current_project

        if not project:
            self.tasks.addItem(QListWidgetItem(tr("tasks.idle")))
            return

        records = project.get("task_history", []) or project.get("result_history", [])
        if not records:
            self.tasks.addItem(QListWidgetItem(tr("tasks.empty")))
            return

        for r in reversed(records[-50:]):
            title = r.get("title") or r.get("category") or ""
            status = r.get("status", "?")
            item = QListWidgetItem(f"[{status}] {title}")
            self.tasks.addItem(item)

    def _clear_history(self) -> None:
        window = self.window()
        if hasattr(window, "_ctx"):
            project = window._ctx.project_service.current_project
            if project:
                project["task_history"] = []
                project["result_history"] = []
                window._ctx.project_service.mark_dirty()
                self.refresh()

    def retranslate_ui(self) -> None:
        self.refresh_btn.setText(tr("action.refresh"))
        self.clear_btn.setText(tr("action.clear"))
        self.refresh()
