"""Undo/Redo 命令管理器"""

from abc import ABC, abstractmethod
from typing import Callable, List


class Command(ABC):
    """可撤销的命令基类"""

    @abstractmethod
    def execute(self): ...

    @abstractmethod
    def undo(self): ...


class UndoManager:
    """命令栈管理器（最多保存 50 步）"""

    def __init__(self, max_history: int = 50, on_change: Callable = None):
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_history = max_history
        self._on_change = on_change

    def execute(self, cmd: Command):
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._notify()

    def record_applied(self, cmd: Command):
        """Record a command whose effect has already been applied by interactive dragging."""
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._notify()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        self._notify()
        return True

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify()

    def _notify(self):
        if self._on_change:
            self._on_change(self.can_undo, self.can_redo)


# ====================== 矢量编辑专用命令 ======================
class MoveFeatureCommand(Command):
    """移动要素命令"""

    def __init__(self, layer, feat_idx, dx, dy, redraw_cb):
        self.layer = layer
        self.feat_idx = feat_idx
        self.dx = dx
        self.dy = dy
        self._redraw = redraw_cb

    def execute(self):
        from core.vector_processing import invalidate_shapely_cache, move_feature

        feat = self.layer["features"][self.feat_idx]
        self.layer["features"][self.feat_idx] = move_feature(feat, self.dx, self.dy)
        invalidate_shapely_cache(self.layer, self.feat_idx)
        self._redraw()

    def undo(self):
        from core.vector_processing import invalidate_shapely_cache, move_feature

        feat = self.layer["features"][self.feat_idx]
        self.layer["features"][self.feat_idx] = move_feature(feat, -self.dx, -self.dy)
        invalidate_shapely_cache(self.layer, self.feat_idx)
        self._redraw()


class DeleteFeatureCommand(Command):
    """删除要素命令"""

    def __init__(self, layer, feat_idx, feature, redraw_cb):
        self.layer = layer
        self.feat_idx = feat_idx
        self._feature = feature
        self._redraw = redraw_cb

    def execute(self):
        from core.vector_processing import invalidate_shapely_cache

        self.layer["features"].pop(self.feat_idx)
        invalidate_shapely_cache(self.layer)
        self._redraw()

    def undo(self):
        from core.vector_processing import invalidate_shapely_cache

        self.layer["features"].insert(self.feat_idx, self._feature)
        invalidate_shapely_cache(self.layer, self.feat_idx)
        self._redraw()


class EditVertexCommand(Command):
    """编辑顶点命令"""

    def __init__(self, layer, feat_idx, vertex_idx, old_pos, new_pos, geom_type, redraw_cb):
        self.layer = layer
        self.feat_idx = feat_idx
        self.vertex_idx = vertex_idx
        self.old_pos = list(old_pos)
        self.new_pos = list(new_pos)
        self.geom_type = geom_type
        self._redraw = redraw_cb

    def _apply(self, pos):
        from core.vector_processing import invalidate_shapely_cache

        feat = self.layer["features"][self.feat_idx]
        g = feat["geometry"]
        if self.geom_type == "Point":
            g["coordinates"] = pos
        elif self.geom_type == "LineString":
            g["coordinates"][self.vertex_idx] = pos
        elif self.geom_type == "Polygon":
            ring = g["coordinates"][0]
            ring[self.vertex_idx] = pos
            if self.vertex_idx == 0 and len(ring) > 1:
                ring[-1] = pos.copy()
            elif self.vertex_idx == len(ring) - 1 and len(ring) > 1:
                ring[0] = pos.copy()
        invalidate_shapely_cache(self.layer, self.feat_idx)

    def execute(self):
        self._apply(self.new_pos)
        self._redraw()

    def undo(self):
        self._apply(self.old_pos)
        self._redraw()
