"""Octree LOD manager for large point clouds.

Builds an octree per layer and queries view-dependent LOD levels.
This keeps interactive frame rates even with 100M+ point datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from common.logger import logger

_MAX_DEPTH = 8
_MIN_POINTS_PER_NODE = 1000
_DEFAULT_MAX_POINTS_PER_FRAME = 1_000_000


@dataclass
class LODQueryResult:
    """Visible subset returned by the LOD manager."""

    points: np.ndarray
    indices: np.ndarray
    colors: Optional[np.ndarray] = None
    classifications: Optional[np.ndarray] = None


class OctreeNode:
    """Lightweight octree node with geometry cache."""

    __slots__ = ("center", "half", "depth", "children", "point_indices", "_points", "_sampled")

    def __init__(self, center: np.ndarray, half: float, depth: int = 0):
        self.center = center.astype(np.float32)
        self.half = half
        self.depth = depth
        self.children: list[OctreeNode] = []
        self.point_indices: np.ndarray = np.array([], dtype=np.int64)
        self._points: Optional[np.ndarray] = None
        self._sampled: Optional[np.ndarray] = None

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def has_points(self) -> bool:
        return len(self.point_indices) > 0

    def sample_factor(self, max_points_per_node: int) -> int:
        n = len(self.point_indices)
        if n <= max_points_per_node:
            return 1
        return max(1, n // max_points_per_node)


class LODManager:
    """Manages per-layer octrees for dynamic level-of-detail rendering."""

    def __init__(
        self,
        max_points_per_frame: int = _DEFAULT_MAX_POINTS_PER_FRAME,
        min_points_per_node: int = _MIN_POINTS_PER_NODE,
        max_depth: int = _MAX_DEPTH,
    ):
        self.max_points_per_frame = max_points_per_frame
        self.min_points_per_node = min_points_per_node
        self.max_depth = max_depth
        self._octrees: dict[str, OctreeNode] = {}
        self._full_points: dict[str, np.ndarray] = {}
        self._full_colors: dict[str, Optional[np.ndarray]] = {}
        self._full_classifications: dict[str, Optional[np.ndarray]] = {}

    def build(
        self,
        layer_id: str,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        classifications: Optional[np.ndarray] = None,
    ) -> OctreeNode:
        """Build an octree for a layer's point cloud."""
        points = np.asarray(points, dtype=np.float32)
        if points.size == 0:
            points = np.empty((0, 3), dtype=np.float32)
        else:
            points = points.reshape(-1, points.shape[-1])
            if points.shape[1] < 3:
                raise ValueError("LODManager.build requires points with at least 3 columns")
            points = points[:, :3]
        if len(points) == 0:
            raise ValueError("LODManager.build requires at least one point")
        self._full_points[layer_id] = points
        self._full_colors[layer_id] = (
            np.asarray(colors, dtype=np.float32)[:, :3]
            if colors is not None and len(colors) == len(points)
            else None
        )
        self._full_classifications[layer_id] = (
            np.asarray(classifications, dtype=np.int32).reshape(-1)
            if classifications is not None and len(classifications) == len(points)
            else None
        )

        mins = points.min(axis=0)
        maxs = points.max(axis=0)
        center = (mins + maxs) / 2
        half = float(np.max(maxs - mins)) / 2 + 1e-6

        root = OctreeNode(center, half, depth=0)
        root.point_indices = np.arange(len(points), dtype=np.int64)
        self._subdivide(root, points)
        self._octrees[layer_id] = root

        total = len(points)
        logger.info(
            f"LOD octree built for {layer_id}: {total} points, "
            f"half={half:.1f}m, max_depth={self.max_depth}"
        )
        return root

    def _subdivide(self, node: OctreeNode, all_points: np.ndarray):
        if node.depth >= self.max_depth:
            return
        if len(node.point_indices) < self.min_points_per_node:
            return

        indices = node.point_indices
        pts = all_points[indices]
        child_half = node.half / 2

        for ox in (-1, 1):
            for oy in (-1, 1):
                for oz in (-1, 1):
                    child_center = node.center + np.array(
                        [ox * child_half, oy * child_half, oz * child_half], dtype=np.float32
                    )
                    child = OctreeNode(child_center, child_half, node.depth + 1)

                    in_child = (
                        (pts[:, 0] >= child_center[0] - child_half)
                        & (pts[:, 0] < child_center[0] + child_half)
                        & (pts[:, 1] >= child_center[1] - child_half)
                        & (pts[:, 1] < child_center[1] + child_half)
                        & (pts[:, 2] >= child_center[2] - child_half)
                        & (pts[:, 2] < child_center[2] + child_half)
                    )
                    child_indices = indices[in_child]
                    if len(child_indices) == 0:
                        continue
                    child.point_indices = child_indices
                    self._subdivide(child, all_points)
                    node.children.append(child)

    def query(
        self,
        layer_id: str,
        camera_pos: np.ndarray,
        view_dir: np.ndarray,
        fov_deg: float = 60.0,
        aspect: float = 1.6,
    ) -> tuple[np.ndarray, Optional[np.ndarray]]:
        """Query visible points for the current camera state.

        Returns (points, colors) arrays suitable for rendering.
        """
        result = self.query_detail(layer_id, camera_pos, view_dir, fov_deg=fov_deg, aspect=aspect)
        return result.points, result.colors

    def query_detail(
        self,
        layer_id: str,
        camera_pos: np.ndarray,
        view_dir: np.ndarray,
        fov_deg: float = 60.0,
        aspect: float = 1.6,
    ) -> LODQueryResult:
        """Query visible points and return original point indices plus attributes."""
        root = self._octrees.get(layer_id)
        if root is None:
            return self._empty_result()

        all_pts = self._full_points.get(layer_id)
        all_colors = self._full_colors.get(layer_id)
        all_classes = self._full_classifications.get(layer_id)
        if all_pts is None:
            return self._empty_result()

        selected = []
        budget = self.max_points_per_frame
        self._query_node(root, all_pts, camera_pos, view_dir, fov_deg, selected, budget)

        if not selected:
            return self._empty_result()

        indices = np.concatenate([n.point_indices for n in selected])
        if len(indices) > self.max_points_per_frame:
            sample = np.linspace(0, len(indices) - 1, self.max_points_per_frame, dtype=np.int64)
            indices = indices[sample]

        return LODQueryResult(
            points=all_pts[indices],
            indices=indices.astype(np.int64, copy=False),
            colors=all_colors[indices] if all_colors is not None else None,
            classifications=all_classes[indices] if all_classes is not None else None,
        )

    def _query_node(
        self,
        node: OctreeNode,
        all_pts: np.ndarray,
        camera_pos: np.ndarray,
        view_dir: np.ndarray,
        fov_deg: float,
        selected: list,
        budget: int,
    ) -> None:
        if sum(len(n.point_indices) for n in selected) >= budget:
            return

        if not self._in_frustum(node, camera_pos, view_dir, fov_deg):
            return

        dist = float(np.linalg.norm(node.center - camera_pos))
        depth_ratio = min(1.0, dist / (node.half * 10 + 1e-6))

        if node.is_leaf or depth_ratio > 0.7 or node.depth >= self.max_depth:
            if node.has_points():
                selected.append(node)
            return

        for child in node.children:
            self._query_node(child, all_pts, camera_pos, view_dir, fov_deg, selected, budget)

    def _in_frustum(
        self, node: OctreeNode, camera_pos: np.ndarray, view_dir: np.ndarray, fov_deg: float
    ) -> bool:
        to_center = node.center - camera_pos
        dist = float(np.linalg.norm(to_center))
        if dist < node.half * 1.5:
            return True

        to_center /= dist
        cos_angle = float(np.dot(to_center, view_dir))
        half_fov_rad = np.radians(fov_deg / 2)
        angle_threshold = np.cos(half_fov_rad + np.radians(30))

        return cos_angle > angle_threshold or dist < node.half * 3

    def get_full_points(self, layer_id: str) -> Optional[np.ndarray]:
        return self._full_points.get(layer_id)

    def get_full_classifications(self, layer_id: str) -> Optional[np.ndarray]:
        return self._full_classifications.get(layer_id)

    def set_render_budget(self, max_points_per_frame: int) -> None:
        self.max_points_per_frame = max(1, int(max_points_per_frame))

    def remove_layer(self, layer_id: str) -> None:
        self._octrees.pop(layer_id, None)
        self._full_points.pop(layer_id, None)
        self._full_colors.pop(layer_id, None)
        self._full_classifications.pop(layer_id, None)

    def clear(self) -> None:
        self._octrees.clear()
        self._full_points.clear()
        self._full_colors.clear()
        self._full_classifications.clear()

    @staticmethod
    def _empty_result() -> LODQueryResult:
        return LODQueryResult(
            points=np.empty((0, 3), dtype=np.float32),
            indices=np.empty(0, dtype=np.int64),
        )

    @staticmethod
    def estimate_lod_level(
        dist: float, bbox_diag: float, min_level: int = 0, max_level: int = 7
    ) -> int:
        frac = np.clip(dist / (bbox_diag + 1e-6), 0.0, 1.0)
        return int(min_level + frac * (max_level - min_level))
