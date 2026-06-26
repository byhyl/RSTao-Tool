"""Properties panel — shows project and per-resource details."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ..i18n import tr


class PropertiesDock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: dict | None = None
        self._project_path: str | None = None
        self._resource: dict | None = None

        self.title = QLabel()
        self.title.setObjectName("AccentText")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.title)
        layout.addWidget(self.details)
        self.retranslate_ui()

    def show_project(self, project: dict | None, project_path: str | None = None) -> None:
        self._project = project
        self._project_path = project_path
        self._resource = None
        if not project:
            self.details.setPlainText(tr("properties.none"))
            return
        lines = [
            f"{tr('properties.name')}: {project.get('project_name', tr('project.untitled'))}",
            f"{tr('properties.path')}: {project_path or tr('properties.unsaved')}",
            f"{tr('properties.schema')}: {project.get('schema_version', tr('properties.unknown'))}",
            f"{tr('properties.modified')}: {project.get('modified_time', '-')}",
            f"{tr('properties.resources')}: {len(project.get('resources', []))}",
            f"{tr('properties.data_sources')}: {len(project.get('data_sources', []))}",
            f"{tr('properties.results')}: {len(project.get('result_history', []))}",
        ]
        self.details.setPlainText("\n".join(lines))

    def show_resource(self, resource: dict | None) -> None:
        self._resource = resource
        if not resource:
            self.show_project(self._project, self._project_path)
            return
        lines = []
        for key in ["name", "source_path", "source_type", "extension",
                     "size_bytes", "crs", "epsg", "width", "height",
                     "bands", "dtype", "point_count", "face_count", "dimensions",
                     "format_detail", "warning"]:
            val = resource.get(key)
            if val is not None and val != "":
                lines.append(f"{tr(f'properties.{key}')}: {val}")
        if not lines:
            lines.append(tr("properties.none"))
        self.details.setPlainText("\n".join(lines))

    def retranslate_ui(self) -> None:
        self.title.setText(tr("properties.selection"))
        if self._resource:
            self.show_resource(self._resource)
        else:
            self.show_project(self._project, self._project_path)
