"""Undo manager behavior for vector editing commands."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vector_processing import create_new_layer, create_polygon_feature
from ui.undo_manager import EditVertexCommand, UndoManager


def test_record_applied_vertex_edit_can_undo_and_redo_polygon_closure():
    layer = create_new_layer("poly", "Polygon")
    layer["features"] = [create_polygon_feature([(0, 0), (10, 0), (10, 10), (0, 10)])]
    redraws = []

    cmd = EditVertexCommand(
        layer,
        0,
        0,
        old_pos=(0, 0),
        new_pos=(2, 3),
        geom_type="Polygon",
        redraw_cb=lambda: redraws.append(True),
    )
    cmd.execute()
    manager = UndoManager()
    manager.record_applied(cmd)

    ring = layer["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [2, 3]
    assert ring[-1] == [2, 3]

    assert manager.undo() is True
    ring = layer["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [0, 0]
    assert ring[-1] == [0, 0]

    assert manager.redo() is True
    ring = layer["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [2, 3]
    assert ring[-1] == [2, 3]
