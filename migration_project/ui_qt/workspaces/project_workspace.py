"""Project workspace for the Qt preview UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..i18n import tr


class ProjectWorkspace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: dict | None = None
        self._project_path: str | None = None

        card = QFrame()
        card.setObjectName("WorkspaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 28, 30, 28)
        card_layout.setSpacing(10)

        self.title = QLabel()
        self.title.setObjectName("AppTitle")

        self.summary = QLabel()
        self.summary.setObjectName("MutedText")
        self.summary.setWordWrap(True)

        card_layout.addWidget(self.title)
        card_layout.addWidget(self.summary)
        card_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(card)
        self.retranslate_ui()

    def show_project(self, project: dict | None, project_path: str | None = None) -> None:
        self._project = project
        self._project_path = project_path
        self._update_summary()

    def retranslate_ui(self) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        self.title.setText(tr("project_workspace.title"))
        if not self._project:
            self.summary.setText(tr("project_workspace.empty"))
            return

        project_name = self._project.get("project_name") or tr("project.untitled")
        project_path = self._project_path or tr("project_workspace.unsaved")
        resource_count = len(self._project.get("resources", []))
        data_source_count = len(self._project.get("data_sources", []))
        result_count = len(self._project.get("result_history", []))

        if self._project_path:
            project_path = str(Path(self._project_path))

        lines = [
            f"{tr('project_workspace.name')}: {project_name}",
            f"{tr('project_workspace.path')}: {project_path}",
            f"{tr('project_workspace.resources')}: {resource_count}",
            f"{tr('project_workspace.data_sources')}: {data_source_count}",
            f"{tr('project_workspace.results')}: {result_count}",
        ]
        self.summary.setText("\n".join(lines))
