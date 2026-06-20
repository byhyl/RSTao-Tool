import sys
from types import SimpleNamespace

import numpy as np

from core.project_manager import ProjectManager
from core.resource_manager import create_resource_record, read_scene_preview


def test_ascii_pcd_resource_metadata_and_preview(tmp_path):
    pcd = tmp_path / "cloud.pcd"
    pcd.write_text(
        "\n".join(
            [
                "# .PCD v0.7",
                "VERSION 0.7",
                "FIELDS x y z",
                "SIZE 4 4 4",
                "TYPE F F F",
                "COUNT 1 1 1",
                "WIDTH 3",
                "HEIGHT 1",
                "POINTS 3",
                "DATA ascii",
                "0 0 0",
                "1 2 3",
                "-1 4 2",
            ]
        ),
        encoding="utf-8",
    )

    record = create_resource_record(pcd)
    preview = read_scene_preview(pcd)

    assert record["source_type"] == "pointcloud"
    assert record["point_count"] == 3
    assert record["format_detail"].startswith("PCD")
    assert preview.vertices.shape == (3, 3)


def test_obj_resource_metadata_and_preview(tmp_path):
    obj = tmp_path / "mesh.obj"
    obj.write_text(
        "\n".join(
            [
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",
            ]
        ),
        encoding="utf-8",
    )

    record = create_resource_record(obj)
    preview = read_scene_preview(obj)

    assert record["source_type"] == "mesh"
    assert record["vertex_count"] == 3
    assert record["face_count"] == 1
    assert preview.vertices.shape == (3, 3)
    assert preview.faces.shape == (1, 3)


def test_trimesh_metadata_backend_is_used(tmp_path, monkeypatch):
    obj = tmp_path / "mesh.obj"
    obj.write_text("# parsed by fake trimesh\n", encoding="utf-8")

    fake_mesh = SimpleNamespace(
        vertices=np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=int),
    )
    fake_trimesh = SimpleNamespace(load=lambda *_args, **_kwargs: fake_mesh)
    monkeypatch.setitem(sys.modules, "trimesh", fake_trimesh)

    record = create_resource_record(obj)

    assert record["vertex_count"] == 3
    assert record["face_count"] == 1
    assert record["bounds"] == (0.0, 2.0, 0.0, 3.0, 0.0, 0.0)


def test_project_manager_resource_crud(tmp_path):
    pm = ProjectManager()
    source_path = str(tmp_path / "a.pcd")
    pm.current_project = {
        "project_name": "demo",
        "data_sources": [{"source_path": source_path, "source_type": "pointcloud"}],
    }
    resource = {
        "resource_id": "abc",
        "source_path": source_path,
        "name": "a.pcd",
        "source_type": "pointcloud",
    }

    pm.add_resource(resource)
    pm.update_resource("abc", visible=False)

    assert pm.get_resources()[0]["visible"] is False
    assert pm.remove_resource("abc") is True
    assert pm.get_resources() == []
    assert pm.current_project["data_sources"] == []
