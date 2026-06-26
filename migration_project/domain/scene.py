"""3D scene graph domain contracts -- extracted from core/scene_graph.py.

No numpy/Open3D dependencies. Geometry data is implementation-layer concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


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
    """A single layer in the 3D scene graph."""

    id: str = ""
    name: str = ""
    layer_type: LayerType = LayerType.POINT_CLOUD
    visible: bool = True
    opacity: float = 1.0
    locked: bool = False
    order: int = 0
    source_path: str = ""
    point_count: int = 0
    face_count: int = 0
    crs: str = ""
    epsg: Optional[int] = None
    point_size: float = 2.0
    color_mode: ColorMode = ColorMode.RGB
    colormap: str = "viridis"
    single_color: tuple[float, float, float] = (0.3, 0.7, 1.0)
    class_colors: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    warning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return self.point_count == 0 and self.face_count == 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "layer_type": self.layer_type.value,
            "visible": self.visible, "opacity": self.opacity,
            "locked": self.locked, "order": self.order,
            "source_path": self.source_path,
            "point_count": self.point_count, "face_count": self.face_count,
            "crs": self.crs, "epsg": self.epsg,
            "point_size": self.point_size,
            "color_mode": self.color_mode.value,
            "colormap": self.colormap,
            "single_color": list(self.single_color),
            "class_colors": {str(k): list(v) for k, v in self.class_colors.items()},
            "warning": self.warning,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SceneLayer:
        lt = d.get("layer_type", "pointcloud")
        if isinstance(lt, str):
            try:
                layer_type = LayerType(lt)
            except ValueError:
                layer_type = LayerType.POINT_CLOUD
        else:
            layer_type = LayerType.POINT_CLOUD

        cm = d.get("color_mode", "rgb")
        if isinstance(cm, str):
            try:
                color_mode = ColorMode(cm)
            except ValueError:
                color_mode = ColorMode.RGB
        else:
            color_mode = ColorMode.RGB

        sc_raw = d.get("single_color", [0.3, 0.7, 1.0])
        if isinstance(sc_raw, list) and len(sc_raw) >= 3:
            single_color = (float(sc_raw[0]), float(sc_raw[1]), float(sc_raw[2]))
        elif isinstance(sc_raw, tuple):
            single_color = sc_raw
        else:
            single_color = (0.3, 0.7, 1.0)

        cc_raw = d.get("class_colors", {})
        class_colors: dict[int, tuple[float, float, float]] = {}
        for k, v in cc_raw.items():
            if isinstance(v, list) and len(v) >= 3:
                class_colors[int(k)] = (float(v[0]), float(v[1]), float(v[2]))
            elif isinstance(v, tuple):
                class_colors[int(k)] = v

        return cls(
            id=d.get("id", ""), name=d.get("name", ""),
            layer_type=layer_type, visible=d.get("visible", True),
            opacity=d.get("opacity", 1.0), locked=d.get("locked", False),
            order=d.get("order", 0), source_path=d.get("source_path", ""),
            point_count=d.get("point_count", 0), face_count=d.get("face_count", 0),
            crs=d.get("crs", ""), epsg=d.get("epsg"),
            point_size=d.get("point_size", 2.0), color_mode=color_mode,
            colormap=d.get("colormap", "viridis"), single_color=single_color,
            class_colors=class_colors, warning=d.get("warning", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class SceneGraph:
    """Container for 3D scene layers with a unified scene CRS."""

    layers: list[SceneLayer] = field(default_factory=list)
    scene_crs: str = ""
    scene_epsg: Optional[int] = None
    background_color: tuple[float, float, float, float] = (0.12, 0.12, 0.14, 1.0)
    show_origin_grid: bool = True
    grid_size: float = 100.0
    grid_spacing: float = 10.0

    @property
    def layer_count(self) -> int:
        return len(self.layers)

    @property
    def visible_layers(self) -> list[SceneLayer]:
        return [ly for ly in self.layers if ly.visible]

    def to_dict(self) -> dict:
        return {
            "scene_crs": self.scene_crs, "scene_epsg": self.scene_epsg,
            "layers": [ly.to_dict() for ly in self.layers],
            "background_color": list(self.background_color),
            "show_origin_grid": self.show_origin_grid,
            "grid_size": self.grid_size, "grid_spacing": self.grid_spacing,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SceneGraph:
        bg = d.get("background_color", [0.12, 0.12, 0.14, 1.0])
        if isinstance(bg, list) and len(bg) >= 4:
            background_color = (float(bg[0]), float(bg[1]), float(bg[2]), float(bg[3]))
        elif isinstance(bg, tuple):
            background_color = bg
        else:
            background_color = (0.12, 0.12, 0.14, 1.0)
        return cls(
            scene_crs=d.get("scene_crs", ""), scene_epsg=d.get("scene_epsg"),
            layers=[SceneLayer.from_dict(ly) for ly in d.get("layers", [])],
            background_color=background_color,
            show_origin_grid=d.get("show_origin_grid", True),
            grid_size=d.get("grid_size", 100.0),
            grid_spacing=d.get("grid_spacing", 10.0),
        )
