"""3D viewer undo / redo support.

Captures scene state snapshots and restores them on Ctrl+Z / Ctrl+Y.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

from common.logger import logger


@dataclass
class SceneSnapshot:
    """Serializable scene state at a point in time."""

    layers_json: list[dict[str, Any]]
    scene_crs: str
    camera_params: Optional[dict[str, Any]] = None


class Viewer3DStateManager:
    """Manages undo/redo stack for 3D viewer operations.

    Usage:
        mgr = Viewer3DStateManager(max_history=50)
        mgr.push(scene_graph)  # snapshot before modifying
        ... modify scene ...
        mgr.undo(scene_graph)  # restore previous state
    """

    def __init__(self, max_history: int = 50):
        self._undo_stack: list[SceneSnapshot] = []
        self._redo_stack: list[SceneSnapshot] = []
        self.max_history = max_history
        self._on_change: Optional[callable] = None

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def set_on_change(self, callback: callable) -> None:
        self._on_change = callback

    def push(self, scene_graph) -> None:
        """Snapshot current scene state onto the undo stack."""
        from core.scene_graph import SceneGraph

        snapshot = SceneSnapshot(
            layers_json=[ly.to_dict() for ly in scene_graph.layers],
            scene_crs=scene_graph.scene_crs,
        )
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._notify()

    def undo(self, scene_graph) -> bool:
        """Restore previous scene state. Returns True on success."""
        if not self._undo_stack:
            return False

        current = SceneSnapshot(
            layers_json=[ly.to_dict() for ly in scene_graph.layers],
            scene_crs=scene_graph.scene_crs,
        )
        self._redo_stack.append(current)

        previous = self._undo_stack.pop()
        self._restore_snapshot(scene_graph, previous)
        self._notify()
        logger.debug(
            f"3D undo: redo stack={len(self._redo_stack)}, undo stack={len(self._undo_stack)}"
        )
        return True

    def redo(self, scene_graph) -> bool:
        """Re-apply previously undone state."""
        if not self._redo_stack:
            return False

        current = SceneSnapshot(
            layers_json=[ly.to_dict() for ly in scene_graph.layers],
            scene_crs=scene_graph.scene_crs,
        )
        self._undo_stack.append(current)

        next_state = self._redo_stack.pop()
        self._restore_snapshot(scene_graph, next_state)
        self._notify()
        logger.debug(
            f"3D redo: redo stack={len(self._redo_stack)}, undo stack={len(self._undo_stack)}"
        )
        return True

    def _restore_snapshot(self, scene_graph, snapshot: SceneSnapshot) -> None:
        from core.scene_graph import SceneLayer

        scene_graph.clear()
        scene_graph.scene_crs = snapshot.scene_crs
        for layer_data in snapshot.layers_json:
            layer = SceneLayer.from_dict(layer_data)
            scene_graph.add_layer(layer)

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.can_undo, self.can_redo)
            except Exception:
                pass

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify()
