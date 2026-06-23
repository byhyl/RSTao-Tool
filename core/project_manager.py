"""Project file management."""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from common.logger import logger
from common.paths import get_settings_dir, migrate_file_once
from core.result_history import make_result_record

SCHEMA_VERSION = 4


def _safe_path_exists(path: str | Path) -> bool:
    try:
        return Path(path).exists()
    except (OSError, ValueError):
        return False


def _safe_path_stat(path: str | Path):
    try:
        return Path(path).stat()
    except (OSError, ValueError):
        return None


class ProjectManager:
    """Create, save, load, and recover RSTao project files."""

    def __init__(self):
        self.current_project = None
        self.project_path: Optional[str] = None
        self.recent_projects = self._load_recent_projects()
        self.max_recent = 10
        self._auto_save_timer = None
        self._auto_save_interval = 180
        self._dirty = False
        self._auto_save_enabled = True
        self._save_lock = threading.Lock()
        self.last_saved_at: Optional[str] = None

    def _load_recent_projects(self):
        config_path = self._recent_projects_config_path()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    projects = config.get("recent_projects", [])
                    return [path for path in projects if isinstance(path, str)]
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_recent_projects(self):
        config_path = self._recent_projects_config_path()
        config = {"recent_projects": self.recent_projects}
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _recent_projects_config_path() -> Path:
        path = get_settings_dir() / "recent_projects.json"
        migrate_file_once([Path(os.path.expanduser("~")) / ".rstao_config"], path)
        return path

    def add_recent_project(self, path):
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        if len(self.recent_projects) > self.max_recent:
            self.recent_projects = self.recent_projects[: self.max_recent]
        self._save_recent_projects()

    def remove_recent_project(self, path):
        if path in self.recent_projects:
            self.recent_projects.remove(path)
            self._save_recent_projects()

    def clear_recent_projects(self):
        self.recent_projects = []
        self._save_recent_projects()

    def prune_missing_recent_projects(self):
        self.recent_projects = [path for path in self.recent_projects if _safe_path_exists(path)]
        self._save_recent_projects()

    def new_project(self, name, save_path):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_project = {
            "schema_version": SCHEMA_VERSION,
            "project_name": name,
            "created_time": now,
            "modified_time": now,
            "current_tab": "特征检测",
            "feature_tab": {},
            "image_processing_tab": {},
            "match_tab": {},
            "vector_tab": {},
            "coordinate_tab": {},
            "detection_tab": {},
            "settings_tab": {},
            "viewer_3d_tab": {},
            "resources": [],
            "data_sources": [],
            "result_history": [],
            "task_history": [],
        }
        self.project_path = save_path
        self.save_project()
        self.add_recent_project(save_path)
        return True

    def save_project(
        self,
        feature_state=None,
        image_processing_state=None,
        match_state=None,
        vector_state=None,
        current_tab=None,
        coordinate_state=None,
        detection_state=None,
        settings_state=None,
        viewer_3d_state=None,
        autosave: bool = False,
    ):
        if not self.current_project or not self.project_path:
            return False

        self.current_project["modified_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_project.setdefault("schema_version", SCHEMA_VERSION)
        if feature_state is not None:
            self.current_project["feature_tab"] = feature_state
        if image_processing_state is not None:
            self.current_project["image_processing_tab"] = image_processing_state
        if match_state is not None:
            self.current_project["match_tab"] = match_state
        if vector_state is not None:
            self.current_project["vector_tab"] = vector_state
        if coordinate_state is not None:
            self.current_project["coordinate_tab"] = coordinate_state
        if detection_state is not None:
            self.current_project["detection_tab"] = detection_state
        if settings_state is not None:
            self.current_project["settings_tab"] = settings_state
        if viewer_3d_state is not None:
            self.current_project["viewer_3d_tab"] = viewer_3d_state
        if current_tab:
            self.current_project["current_tab"] = current_tab

        target = self.get_autosave_path(self.project_path) if autosave else Path(self.project_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not autosave:
                self._backup_project_file(Path(self.project_path))
            self._atomic_write_json(target, self.current_project)
            if not autosave:
                self.discard_autosave(self.project_path)
                self._dirty = False
                self.last_saved_at = datetime.now().strftime("%H:%M:%S")
            return True
        except Exception as e:
            logger.error(f"保存项目失败: {e}", exc_info=True)
            return False

    def load_project(self, path):
        if not _safe_path_exists(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                self.current_project = json.load(f)
            self._migrate_project()
            self.project_path = path
            self.add_recent_project(path)
            return self.current_project
        except Exception as e:
            logger.error(f"加载项目失败: {e}", exc_info=True)
            return False

    def _migrate_project(self):
        if not self.current_project:
            return
        self.current_project.setdefault("schema_version", SCHEMA_VERSION)
        self.current_project.setdefault("feature_tab", {})
        self.current_project.setdefault("image_processing_tab", {})
        self.current_project.setdefault("match_tab", {})
        self.current_project.setdefault("vector_tab", {})
        self.current_project.setdefault("coordinate_tab", {})
        self.current_project.setdefault("detection_tab", {})
        self.current_project.setdefault("settings_tab", {})
        self.current_project.setdefault("viewer_3d_tab", {})
        self.current_project.setdefault("resources", [])
        self.current_project.setdefault("data_sources", [])
        self.current_project.setdefault("result_history", [])
        self.current_project.setdefault("task_history", [])

    def add_data_source(self, source: dict):
        if not self.current_project:
            return None
        sources = self.current_project.setdefault("data_sources", [])
        source_path = source.get("source_path") or source.get("path")
        if source_path:
            sources[:] = [item for item in sources if item.get("source_path") != source_path]
        sources.insert(0, source)
        del sources[200:]
        self.mark_dirty()
        return source

    def add_resource(self, resource: dict):
        if not self.current_project:
            return None
        resources = self.current_project.setdefault("resources", [])
        source_path = resource.get("source_path") or resource.get("path")
        resource_id = resource.get("resource_id")
        if source_path or resource_id:
            resources[:] = [
                item
                for item in resources
                if item.get("source_path") != source_path and item.get("resource_id") != resource_id
            ]
        resource.setdefault("order", len(resources))
        resources.insert(0, resource)
        del resources[500:]
        self.mark_dirty()
        try:
            from core.resource_catalog import record_resource

            record_resource(resource)
        except Exception as e:
            logger.warning(f"更新资源索引失败: {e}")
        return resource

    def remove_resource(self, resource_id: str):
        if not self.current_project:
            return False
        resources = self.current_project.setdefault("resources", [])
        removed_paths = {
            item.get("source_path")
            for item in resources
            if item.get("resource_id") == resource_id and item.get("source_path")
        }
        before = len(resources)
        resources[:] = [item for item in resources if item.get("resource_id") != resource_id]
        changed = len(resources) != before
        if removed_paths:
            sources = self.current_project.setdefault("data_sources", [])
            sources[:] = [
                item
                for item in sources
                if (item.get("source_path") or item.get("path")) not in removed_paths
            ]
        if changed:
            self.mark_dirty()
        return changed

    def update_resource(self, resource_id: str, **updates):
        if not self.current_project:
            return None
        for resource in self.current_project.setdefault("resources", []):
            if resource.get("resource_id") == resource_id:
                resource.update(updates)
                self.mark_dirty()
                return resource
        return None

    def get_resources(self):
        if not self.current_project:
            return []
        return self.current_project.setdefault("resources", [])

    def primary_spatial_ref(self):
        if not self.current_project:
            return None
        for source in self.current_project.get("data_sources", []):
            if source.get("epsg") or source.get("crs") or source.get("wkt"):
                return source
        return None

    def add_result_record(self, category: str, title: str, **kwargs):
        if not self.current_project:
            return None
        record = make_result_record(category, title, **kwargs)
        history = self.current_project.setdefault("result_history", [])
        history.insert(0, record)
        del history[100:]
        self.mark_dirty()
        return record

    def add_task_record(self, title: str, **kwargs):
        if not self.current_project:
            return None
        record = make_result_record("task", title, **kwargs)
        history = self.current_project.setdefault("task_history", [])
        history.insert(0, record)
        del history[100:]
        self.mark_dirty()
        return record

    def close_project(self):
        self._stop_auto_save()
        self.current_project = None
        self.project_path = None
        self._dirty = False

    # ====================== Auto-Save ======================
    def set_auto_save(self, enabled: bool = True, interval: int = 180):
        self._auto_save_enabled = enabled
        self._auto_save_interval = interval
        if enabled and self.project_path:
            self._start_auto_save()

    def _start_auto_save(self):
        self._stop_auto_save()
        if not self._auto_save_enabled:
            return
        self._auto_save_timer = threading.Timer(self._auto_save_interval, self._auto_save_tick)
        self._auto_save_timer.daemon = True
        self._auto_save_timer.start()

    def _stop_auto_save(self):
        if self._auto_save_timer:
            self._auto_save_timer.cancel()
            self._auto_save_timer = None

    def _auto_save_tick(self):
        with self._save_lock:
            if self._dirty and self.current_project and self.project_path:
                self.save_project(autosave=True)
        self._start_auto_save()

    def mark_dirty(self):
        self._dirty = True

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ====================== Crash Recovery ======================
    @staticmethod
    def get_autosave_path(project_path: str | Path) -> Path:
        project = Path(project_path)
        return project.with_name(project.name + ".autosave")

    @staticmethod
    def get_backup_path(project_path: str | Path) -> Path:
        project = Path(project_path)
        return project.with_name(project.name + ".bak")

    def check_backup(self, project_path: str) -> bool:
        project = Path(project_path)
        autosave = self.get_autosave_path(project)
        autosave_stat = _safe_path_stat(autosave)
        if autosave_stat is None:
            return False
        project_stat = _safe_path_stat(project)
        return project_stat is None or autosave_stat.st_mtime > project_stat.st_mtime

    def recover_from_backup(self, project_path: str) -> bool:
        autosave = self.get_autosave_path(project_path)
        if not _safe_path_exists(autosave):
            return False
        try:
            shutil.copy2(str(autosave), project_path)
            self.discard_autosave(project_path)
            return self.load_project(project_path) is not False
        except Exception as e:
            logger.error(f"恢复自动保存失败: {e}", exc_info=True)
            return False

    def discard_autosave(self, project_path: str | Path):
        autosave = self.get_autosave_path(project_path)
        try:
            if _safe_path_exists(autosave):
                autosave.unlink()
        except Exception:
            pass

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict):
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _backup_project_file(self, project_path: Path):
        if not _safe_path_exists(project_path):
            return
        backup_path = self.get_backup_path(project_path)
        try:
            shutil.copy2(project_path, backup_path)
        except Exception as e:
            logger.warning(f"创建项目备份失败: {e}")
