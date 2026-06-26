"""Project and resource tree dock with grouped resources."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr


class ProjectDock(QWidget):
    """Tree view of project structure — resources grouped by kind, data sources, results."""

    resourceSelected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: dict | None = None
        self._project_path: str | None = None
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.tree)
        self.set_empty_state()

    def set_empty_state(self) -> None:
        self.tree.clear()
        root = QTreeWidgetItem([tr("project.none")])
        root.setDisabled(True)
        self.tree.addTopLevelItem(root)

    def set_project(self, project: dict | None, project_path: str | None = None) -> None:
        self._project = project
        self._project_path = project_path
        self.tree.clear()
        if not project:
            self.set_empty_state()
            return

        project_name = project.get("project_name") or tr("project.untitled")
        root = QTreeWidgetItem([project_name])
        root.setExpanded(True)
        self.tree.addTopLevelItem(root)

        if project_path:
            location = QTreeWidgetItem([f"{tr('project.file')}: {Path(project_path).name}"])
            location.setToolTip(0, str(project_path))
            root.addChild(location)

        # Group resources by kind
        resources = project.get("resources", [])
        grouped = self._group_by_kind(resources)
        for kind, items in grouped.items():
            self._add_resource_group(root, f"{kind} ({len(items)})", items)

        self._add_resource_group(root, tr("project.data_sources"), project.get("data_sources", []))
        self._add_resource_group(root, tr("project.results"), project.get("result_history", []))
        self.tree.expandAll()

    def _group_by_kind(self, resources: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for r in resources:
            kind = r.get("source_type") or r.get("kind") or tr("resource.kind.other")
            label = tr(f"resource.kind.{kind}")
            groups.setdefault(label, []).append(r)
        return groups

    def _add_resource_group(self, parent: QTreeWidgetItem, title: str,
                            items: Iterable[dict]) -> None:
        group = QTreeWidgetItem([title])
        parent.addChild(group)
        count = 0
        for item in items or []:
            count += 1
            label = (
                item.get("name")
                or item.get("title")
                or item.get("source_path")
                or item.get("path")
                or tr("project.item", count=count)
            )
            child = QTreeWidgetItem([str(label)])
            path_val = item.get("source_path") or item.get("path")
            if path_val:
                child.setToolTip(0, str(path_val))
            child.setData(0, 256, item)
            group.addChild(child)
        if count == 0:
            empty = QTreeWidgetItem([tr("project.empty")])
            empty.setDisabled(True)
            group.addChild(empty)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, 256)
        if not data:
            return
        menu = QMenu(self)
        remove_action = menu.addAction(tr("action.remove_resource"))
        remove_action.triggered.connect(lambda: self._remove_resource(data))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _remove_resource(self, resource: dict) -> None:
        rid = resource.get("resource_id") or resource.get("id")
        if rid:
            window = self.window()
            if hasattr(window, "_ctx"):
                window._ctx.project_service.remove_resource(rid)
                window._refresh_project_views()

    def retranslate_ui(self) -> None:
        self.set_project(self._project, self._project_path)
