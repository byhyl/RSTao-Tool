"""Project domain contract -- replaces the free-form dict used everywhere."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


SCHEMA_VERSION = 4


@dataclass
class ProjectResource:
    """Lightweight reference to a resource within a project.

    The full resource data lives in the Resource domain object.
    """

    resource_id: str = ""
    order: int = 0
    visible: bool = True
    opacity: float = 1.0
    locked: bool = False

    def to_dict(self) -> dict:
        return {
            "resource_id": self.resource_id, "order": self.order,
            "visible": self.visible, "opacity": self.opacity,
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProjectResource:
        return cls(
            resource_id=d.get("resource_id", ""), order=d.get("order", 0),
            visible=d.get("visible", True), opacity=d.get("opacity", 1.0),
            locked=d.get("locked", False),
        )


@dataclass
class ProjectState:
    """Transient runtime state -- NOT persisted to the project file."""

    is_dirty: bool = False
    last_saved_at: str = ""
    autosave_enabled: bool = True
    autosave_interval: int = 180


@dataclass
class Project:
    """Top-level project data contract.

    Tab states are opaque dicts because each tab defines its own sub-schema.
    Field names in to_dict() use the exact same keys as the existing code
    for JSON serialization compatibility.
    """

    name: str = ""
    path: str = ""
    schema_version: int = SCHEMA_VERSION
    created_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    modified_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    current_tab: str = ""
    feature_tab: dict[str, Any] = field(default_factory=dict)
    image_processing_tab: dict[str, Any] = field(default_factory=dict)
    match_tab: dict[str, Any] = field(default_factory=dict)
    vector_tab: dict[str, Any] = field(default_factory=dict)
    coordinate_tab: dict[str, Any] = field(default_factory=dict)
    detection_tab: dict[str, Any] = field(default_factory=dict)
    settings_tab: dict[str, Any] = field(default_factory=dict)
    viewer_3d_tab: dict[str, Any] = field(default_factory=dict)

    resources: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    result_history: list[dict[str, Any]] = field(default_factory=list)
    task_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_name": self.name,
            "created_time": self.created_time,
            "modified_time": self.modified_time,
            "current_tab": self.current_tab,
            "feature_tab": self.feature_tab,
            "image_processing_tab": self.image_processing_tab,
            "match_tab": self.match_tab,
            "vector_tab": self.vector_tab,
            "coordinate_tab": self.coordinate_tab,
            "detection_tab": self.detection_tab,
            "settings_tab": self.settings_tab,
            "viewer_3d_tab": self.viewer_3d_tab,
            "resources": self.resources,
            "data_sources": self.data_sources,
            "result_history": self.result_history,
            "task_history": self.task_history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        return cls(
            name=d.get("project_name", ""),
            path="",
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            created_time=d.get("created_time", ""),
            modified_time=d.get("modified_time", ""),
            current_tab=d.get("current_tab", ""),
            feature_tab=d.get("feature_tab", {}),
            image_processing_tab=d.get("image_processing_tab", {}),
            match_tab=d.get("match_tab", {}),
            vector_tab=d.get("vector_tab", {}),
            coordinate_tab=d.get("coordinate_tab", {}),
            detection_tab=d.get("detection_tab", {}),
            settings_tab=d.get("settings_tab", {}),
            viewer_3d_tab=d.get("viewer_3d_tab", {}),
            resources=d.get("resources", []),
            data_sources=d.get("data_sources", []),
            result_history=d.get("result_history", []),
            task_history=d.get("task_history", []),
        )

    @property
    def resource_count(self) -> int:
        return len(self.resources)

    @property
    def source_count(self) -> int:
        return len(self.data_sources)

    @property
    def result_count(self) -> int:
        return len(self.result_history)

    @property
    def task_count(self) -> int:
        return len(self.task_history)
