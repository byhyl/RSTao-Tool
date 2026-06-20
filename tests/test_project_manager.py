"""Project save and autosave recovery tests."""

import json
from pathlib import Path

from core import project_manager as project_manager_module
from core.project_manager import ProjectManager


def test_atomic_save_and_autosave_recovery(tmp_path):
    path = tmp_path / "demo.rstao"
    pm = ProjectManager()
    pm.current_project = {
        "project_name": "demo",
        "feature_tab": {},
        "match_tab": {},
        "vector_tab": {},
    }
    pm.project_path = str(path)

    assert pm.save_project()
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["project_name"] == "demo"

    pm.current_project["project_name"] = "autosaved"
    assert pm.save_project(autosave=True)
    autosave = ProjectManager.get_autosave_path(path)
    assert autosave.exists()
    assert pm.check_backup(str(path))

    assert pm.recover_from_backup(str(path))
    assert not autosave.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["project_name"] == "autosaved"


def test_normal_save_discards_autosave(tmp_path):
    path = tmp_path / "demo.rstao"
    pm = ProjectManager()
    pm.current_project = {"project_name": "demo"}
    pm.project_path = str(path)

    assert pm.save_project(autosave=True)
    assert ProjectManager.get_autosave_path(path).exists()
    assert pm.save_project()
    assert not ProjectManager.get_autosave_path(path).exists()
    assert ProjectManager.get_backup_path(path).exists() is False


def test_recent_project_cleanup(tmp_path, monkeypatch):
    existing = tmp_path / "existing.rstao"
    existing.write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.rstao"
    pm = ProjectManager()
    monkeypatch.setattr(pm, "_save_recent_projects", lambda: None)
    pm.recent_projects = [str(missing), str(existing)]

    pm.prune_missing_recent_projects()

    assert pm.recent_projects == [str(existing)]

    pm.remove_recent_project(str(existing))
    assert pm.recent_projects == []


def test_recent_project_cleanup_ignores_inaccessible_paths(monkeypatch):
    pm = ProjectManager()
    monkeypatch.setattr(pm, "_save_recent_projects", lambda: None)
    pm.recent_projects = ["C:/blocked/demo.rstao", "C:/ok/demo.rstao"]

    def fake_exists(path):
        if "blocked" in str(path):
            raise PermissionError("blocked")
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    pm.prune_missing_recent_projects()

    assert pm.recent_projects == ["C:/ok/demo.rstao"]


def test_safe_path_exists_handles_permission_error(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda _path: (_ for _ in ()).throw(PermissionError()))

    assert project_manager_module._safe_path_exists("C:/blocked/demo.rstao") is False
