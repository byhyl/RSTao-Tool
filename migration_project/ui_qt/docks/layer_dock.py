"""Layer dock with visibility toggles and layer management."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr


class LayerDock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: dict | None = None
        self.list_widget = QListWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.list_widget)
        self.retranslate_ui()

    def set_project(self, project: dict | None) -> None:
        self._project = project
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.list_widget.clear()
        if not self._project:
            self.list_widget.addItem(QListWidgetItem(tr("layers.empty")))
            return

        resources = self._project.get("resources", [])
        if not resources:
            self.list_widget.addItem(QListWidgetItem(tr("layers.empty")))
            return

        for resource in resources:
            name = (
                resource.get("name")
                or resource.get("source_path")
                or resource.get("path")
                or tr("project.untitled")
            )
            visible = resource.get("visible", True)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, resource)
            widget = _LayerItemWidget(name, visible)
            widget.visibilityChanged.connect(
                lambda checked, r=resource: self._toggle_visibility(r, checked)
            )
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def _toggle_visibility(self, resource: dict, visible: bool) -> None:
        resource["visible"] = visible
        window = self.window()
        if hasattr(window, "_ctx"):
            window._ctx.project_service.mark_dirty()


class _LayerItemWidget(QWidget):
    from PySide6.QtCore import Signal as _Signal
    visibilityChanged = _Signal(bool)

    def __init__(self, name: str, visible: bool = True):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.checkbox = QCheckBox(name)
        self.checkbox.setChecked(visible)
        self.checkbox.toggled.connect(self.visibilityChanged.emit)
        layout.addWidget(self.checkbox)
