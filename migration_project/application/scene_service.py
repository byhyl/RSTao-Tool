"""3D scene service -- wraps core.scene_graph, core.pointcloud_ops, core.mesh_ops."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from core.scene_graph import SceneGraph, SceneLayer, LayerType, ColorMode
from core.pointcloud_ops import PointCloudData as CorePointCloudData

if TYPE_CHECKING:
    from .app_context import AppContext


class SceneService:
    """Orchestrates 3D scene management and point cloud / mesh operations."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._scene = SceneGraph()

    # -- scene management ------------------------------------------------------

    @property
    def scene(self) -> SceneGraph:
        return self._scene

    def add_layer(self, layer: SceneLayer) -> str:
        return self._scene.add_layer(layer)

    def remove_layer(self, layer_id: str) -> None:
        self._scene.remove_layer(layer_id)

    def get_layer(self, layer_id: str) -> SceneLayer | None:
        return self._scene.get_layer(layer_id)

    def get_visible_layers(self) -> list[SceneLayer]:
        return self._scene.get_visible_layers()

    def clear_scene(self) -> None:
        self._scene.clear()

    def to_dict(self) -> dict:
        return self._scene.to_dict()

    def from_dict(self, d: dict) -> None:
        self._scene = SceneGraph.from_dict(d)

    # -- point cloud operations ------------------------------------------------

    @staticmethod
    def load_pointcloud(path: str) -> CorePointCloudData | None:
        from core.pointcloud_io import load_pointcloud
        return load_pointcloud(path)

    @staticmethod
    def voxel_downsample(data: CorePointCloudData,
                         voxel_size: float) -> CorePointCloudData:
        from core.pointcloud_ops import voxel_downsample_data
        return voxel_downsample_data(data, voxel_size)

    @staticmethod
    def statistical_filter(data: CorePointCloudData, nb_neighbors: int = 20,
                           std_ratio: float = 2.0) -> CorePointCloudData:
        from core.pointcloud_ops import statistical_outlier_removal_data
        return statistical_outlier_removal_data(data, nb_neighbors, std_ratio)

    @staticmethod
    def estimate_normals(data: CorePointCloudData) -> CorePointCloudData:
        from core.pointcloud_ops import estimate_normals_data
        return estimate_normals_data(data)

    @staticmethod
    def cloth_simulation_filter(data: CorePointCloudData) -> CorePointCloudData:
        from core.pointcloud_ops import cloth_simulation_filter
        return cloth_simulation_filter(data)

    # -- mesh operations -------------------------------------------------------

    @staticmethod
    def load_mesh(path: str) -> Any:
        from core.mesh_ops import load_mesh
        return load_mesh(path)

    @staticmethod
    def simplify_mesh(mesh: Any, target_triangles: int) -> Any:
        from core.mesh_ops import simplify_mesh
        return simplify_mesh(mesh, target_triangles)

    # -- GPU -------------------------------------------------------------------

    @staticmethod
    def gpu_available() -> bool:
        from core.gpu_accel import has_gpu
        return has_gpu()
