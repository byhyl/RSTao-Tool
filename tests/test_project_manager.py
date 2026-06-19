"""Project save and autosave recovery tests."""

import json
from pathlib import Path

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
