"""Project CRUD orchestration.  Wraps core.project_manager.ProjectManager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.logger import logger
from core.project_manager import ProjectManager

if TYPE_CHECKING:
    from .app_context import AppContext


class ProjectService:
    """Thin orchestration layer over ProjectManager.

    Provides a dict-based interface for panel states so UI code doesn't
    need to know about the individual state kwargs.
    """

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._pm = ProjectManager()

    # -- project CRUD -------------------------------------------------------

    def new_project(self, name: str, save_path: str) -> bool:
        return self._pm.new_project(name, save_path)

    def load_project(self, path: str) -> dict | None:
        return self._pm.load_project(path)

    def open_project(self, path: str) -> dict | None:
        """Load a project, handling backup check/recovery automatically."""
        if not path:
            return None
        if self._pm.check_backup(path):
            if self._pm.recover_from_backup(path):
                logger.info("已从自动保存恢复项目")
        project = self._pm.load_project(path)
        if project:
            return project
        return None

    def save_project(self, **kwargs) -> bool:
        return self._pm.save_project(**kwargs)

    def save_project_as(self, name: str, save_path: str) -> bool:
        if not self._pm.current_project:
            return False
        self._pm.current_project["project_name"] = name
        self._pm.project_path = save_path
        return self._pm.save_project()

    def close_project(self) -> None:
        self._pm.close_project()

    # -- queries ------------------------------------------------------------

    @property
    def current_project(self) -> dict | None:
        return self._pm.current_project

    @property
    def project_path(self) -> str | None:
        return self._pm.project_path

    @property
    def is_dirty(self) -> bool:
        return self._pm.is_dirty

    def mark_dirty(self) -> None:
        self._pm.mark_dirty()

    def last_saved_at(self) -> str | None:
        return self._pm.last_saved_at

    # -- recent projects ---------------------------------------------------

    def get_recent_projects(self) -> list[str]:
        return self._pm.recent_projects

    def add_recent_project(self, path: str) -> None:
        self._pm.add_recent_project(path)

    def remove_recent_project(self, path: str) -> None:
        self._pm.remove_recent_project(path)

    def clear_recent_projects(self) -> None:
        self._pm.clear_recent_projects()

    def prune_missing_recent_projects(self) -> None:
        self._pm.prune_missing_recent_projects()

    # -- resources & data sources -------------------------------------------

    def add_resource(self, resource: dict) -> dict | None:
        return self._pm.add_resource(resource)

    def add_data_source(self, source: dict) -> dict | None:
        return self._pm.add_data_source(source)

    def remove_resource(self, resource_id: str) -> bool:
        return self._pm.remove_resource(resource_id)

    def get_resources(self) -> list[dict]:
        return self._pm.get_resources()

    def primary_spatial_ref(self) -> dict | None:
        return self._pm.primary_spatial_ref()

    # -- result records ----------------------------------------------------

    def add_result_record(self, category: str, title: str, **kwargs) -> dict | None:
        return self._pm.add_result_record(category, title, **kwargs)

    def add_task_record(self, title: str, **kwargs) -> dict | None:
        return self._pm.add_task_record(title, **kwargs)

    # -- backup / recovery -------------------------------------------------

    def check_backup(self, path: str) -> bool:
        return self._pm.check_backup(path)

    def recover_from_backup(self, path: str) -> bool:
        return self._pm.recover_from_backup(path)
