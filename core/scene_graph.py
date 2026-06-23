"""3D scene graph with layer management, CRS unification, and Open3D geometry references.

The SceneGraph is the single source of truth for all 3D data visible in the viewer.
Every layer carries its own CRS; the graph reprojects on demand to a shared scene CRS.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np

from common.logger import logger


class LayerType(Enum):
    POINT_CLOUD = "pointcloud"
    MESH = "mesh"
    DEM = "dem"
    VECTOR_3D = "vector_3d"
    IMAGE_OVERLAY = "image"


class ColorMode(Enum):
    RGB = "rgb"
    CLASSIFICATION = "classification"
    ELEVATION = "elevation"
    INTENSITY = "intensity"
    NORMAL = "normal"
    SINGLE = "single"


@dataclass
class SceneLayer:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    layer_type: LayerType = LayerType.POINT_CLOUD
    visible: bool = True
    opacity: float = 1.0
    locked: bool = False
    order: int = 0
    geometry: Any = None
    lod_geometry: Any = None
    source_path: str = ""
    point_count: int = 0
    face_count: int = 0
    crs: str = ""
    epsg: Optional[int] = None
    geo_transform: Optional[tuple[float, ...]] = None
    bbox_min: Optional[np.ndarray] = None
    bbox_max: Optional[np.ndarray] = None
    point_size: float = 2.0
    color_mode: ColorMode = ColorMode.RGB
    colormap: str = "viridis"
    single_color: tuple[float, float, float] = (0.3, 0.7, 1.0)
    class_colors: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    classification_field: str = "classification"
    attributes: dict[str, np.ndarray] = field(default_factory=dict)
    warning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_geometry(self) -> bool:
        return self.geometry is not None

    @property
    def is_empty(self) -> bool:
        return self.point_count == 0 and self.face_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "layer_type": self.layer_type.value,
            "visible": self.visible,
            "opacity": self.opacity,
            "locked": self.locked,
            "order": self.order,
            "source_path": self.source_path,
            "point_count": self.point_count,
            "face_count": self.face_count,
            "crs": self.crs,
            "epsg": self.epsg,
            "point_size": self.point_size,
            "color_mode": self.color_mode.value,
            "colormap": self.colormap,
            "single_color": self.single_color,
            "warning": self.warning,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneLayer":
        layer = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
            layer_type=LayerType(data.get("layer_type", "pointcloud")),
            visible=data.get("visible", True),
            opacity=data.get("opacity", 1.0),
            locked=data.get("locked", False),
            order=data.get("order", 0),
            source_path=data.get("source_path", ""),
            point_count=data.get("point_count", 0),
            face_count=data.get("face_count", 0),
            crs=data.get("crs", ""),
            epsg=data.get("epsg"),
            point_size=data.get("point_size", 2.0),
            color_mode=ColorMode(data.get("color_mode", "rgb")),
            colormap=data.get("colormap", "viridis"),
            single_color=tuple(data.get("single_color", (0.3, 0.7, 1.0))),
            warning=data.get("warning", ""),
            metadata=data.get("metadata", {}),
        )
        return layer


@dataclass
class SceneGraph:
    """Container managing all 3D layers with unified CRS."""

    layers: list[SceneLayer] = field(default_factory=list)
    scene_crs: str = ""
    scene_epsg: Optional[int] = None
    background_color: tuple[float, float, float, float] = (0.12, 0.12, 0.14, 1.0)
    show_origin_grid: bool = True
    grid_size: float = 100.0
    grid_spacing: float = 10.0

    def add_layer(self, layer: SceneLayer) -> str:
        layer.order = len(self.layers)
        self.layers.append(layer)
        logger.info(f"SceneGraph: added layer '{layer.name}' ({layer.layer_type.value})")
        return layer.id

    def remove_layer(self, layer_id: str) -> bool:
        for i, layer in enumerate(self.layers):
            if layer.id == layer_id:
                self.layers.pop(i)
                logger.info(f"SceneGraph: removed layer '{layer.name}'")
                return True
        return False

    def get_layer(self, layer_id: str) -> Optional[SceneLayer]:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def get_visible_layers(self) -> list[SceneLayer]:
        return [ly for ly in self.layers if ly.visible]

    def move_layer(self, layer_id: str, new_order: int) -> None:
        layer = self.get_layer(layer_id)
        if layer is None:
            return
        self.layers.remove(layer)
        self.layers.insert(max(0, min(new_order, len(self.layers))), layer)
        for i, ly in enumerate(self.layers):
            ly.order = i

    def clear(self) -> None:
        self.layers.clear()

    def set_scene_crs(self, crs: str, epsg: Optional[int] = None) -> None:
        self.scene_crs = crs
        self.scene_epsg = epsg

    def reproject_all_to(self, target_crs: str) -> None:
        try:
            from pyproj import Transformer
        except ImportError:
            logger.warning("pyproj not available; skipping CRS reprojection")
            return
        for layer in self.layers:
            if not layer.crs or layer.crs == target_crs:
                continue
            try:
                transformer = Transformer.from_crs(layer.crs, target_crs, always_xy=True)
                geom = layer.geometry
                if geom is None:
                    continue
                pts = np.asarray(geom.points, dtype=np.float64)
                if pts.size == 0:
                    continue
                x, y = transformer.transform(pts[:, 0], pts[:, 1])
                pts[:, 0] = x
                pts[:, 1] = y
                geom.points = _as_o3d_vector(pts.astype(np.float32))
                layer.crs = target_crs
                layer.epsg = None
                logger.debug(f"Reprojected layer '{layer.name}': -> {target_crs}")
            except Exception as exc:
                logger.warning(f"Failed to reproject layer '{layer.name}': {exc}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_crs": self.scene_crs,
            "scene_epsg": self.scene_epsg,
            "layers": [ly.to_dict() for ly in self.layers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneGraph":
        sg = cls(
            scene_crs=data.get("scene_crs", ""),
            scene_epsg=data.get("scene_epsg"),
        )
        for layer_data in data.get("layers", []):
            sg.add_layer(SceneLayer.from_dict(layer_data))
        return sg


def _as_o3d_vector(arr: np.ndarray):
    import open3d as o3d

    return o3d.utility.Vector3dVector(arr)


# ---- Color utilities shared across the 3D module ----

_DEFAULT_CLASS_COLORS: dict[int, tuple[float, float, float]] = {
    0: (0.5, 0.5, 0.5),
    1: (0.8, 0.8, 0.8),
    2: (0.35, 0.55, 0.25),
    3: (0.2, 0.7, 0.3),
    4: (0.0, 0.85, 0.1),
    5: (0.0, 0.6, 0.1),
    6: (0.85, 0.2, 0.2),
    7: (0.3, 0.3, 0.3),
    8: (0.85, 0.85, 0.0),
    9: (0.0, 0.2, 0.8),
    10: (0.7, 0.6, 0.1),
    11: (0.3, 0.3, 0.3),
    12: (0.6, 0.3, 0.7),
    13: (0.8, 0.5, 0.3),
    14: (0.8, 0.7, 0.1),
    15: (0.9, 0.5, 0.1),
    16: (0.9, 0.6, 0.2),
    17: (0.5, 0.8, 0.9),
    18: (0.8, 0.2, 0.5),
}


def get_classification_color(class_id: int) -> tuple[float, float, float]:
    return _DEFAULT_CLASS_COLORS.get(class_id, (0.5, 0.5, 0.5))


def apply_colormap(
    values: np.ndarray,
    cmap_name: str = "viridis",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> np.ndarray:
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(cmap_name)
    vmin = float(np.nanmin(values)) if vmin is None else vmin
    vmax = float(np.nanmax(values)) if vmax is None else vmax
    span = vmax - vmin
    normed = np.clip((values - vmin) / span, 0.0, 1.0) if span > 0 else np.zeros_like(values)
    return cmap(normed)[:, :3].astype(np.float32)
