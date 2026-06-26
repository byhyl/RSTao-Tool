"""Vector geospatial operations -- wraps core.vector_processing and data.vector_io."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.logger import logger
from core.spatial_reference import read_vector_spatial_ref
from data.vector_io import read_shp, save_shp, save_dwg

if TYPE_CHECKING:
    from .app_context import AppContext


class VectorService:
    """Vector operations service."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    # -- I/O ------------------------------------------------------------------

    def read(self, path: str) -> dict[str, Any] | None:
        try:
            return read_shp(str(path))
        except Exception as exc:
            logger.debug("读取矢量文件失败 %s: %s", path, exc)
            return None

    def save(self, data: dict[str, Any], path: str) -> bool:
        try:
            save_shp(data, str(path))
            return True
        except Exception as exc:
            logger.debug("保存矢量文件失败 %s: %s", path, exc)
            return False

    def save_dxf(self, data: dict[str, Any], path: str) -> bool:
        try:
            save_dwg(data, str(path))  # data/vector_io.py exports save_dwg (which handles DXF via ezdxf)
            return True
        except Exception as exc:
            logger.debug("保存DXF文件失败 %s: %s", path, exc)
            return False

    def supported_formats(self) -> list[str]:
        return [".shp", ".geojson", ".gpkg", ".dxf"]

    # -- spatial reference -----------------------------------------------------

    def spatial_ref(self, path: str):
        try:
            return read_vector_spatial_ref(path)
        except Exception as exc:
            logger.debug("读取矢量空间参考失败 %s: %s", path, exc)
            return None

    # -- geometry creation (delegates to core.vector_processing) ----------------

    def create_layer(self, name: str, geom_type: str) -> dict[str, Any]:
        from core.vector_processing import create_new_layer
        return create_new_layer(name, geom_type)

    def create_point_feature(self, x: float, y: float,
                             properties: dict[str, Any] | None = None) -> dict[str, Any]:
        from core.vector_processing import create_point_feature
        return create_point_feature(x, y, properties)

    def create_line_feature(self, points: list[tuple[float, float]],
                            properties: dict[str, Any] | None = None) -> dict[str, Any]:
        from core.vector_processing import create_line_feature
        return create_line_feature(points, properties)

    def create_polygon_feature(self, points: list[tuple[float, float]],
                               properties: dict[str, Any] | None = None) -> dict[str, Any]:
        from core.vector_processing import create_polygon_feature
        return create_polygon_feature(points, properties)

    def move_feature(self, feature: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
        from core.vector_processing import move_feature
        return move_feature(feature, dx, dy)

    def select_feature(self, layers: list[dict[str, Any]], x: float, y: float,
                       tolerance: float = 5.0) -> tuple | None:
        from core.vector_processing import select_feature
        return select_feature(layers, x, y, tolerance)

    # -- property editing ------------------------------------------------------

    def update_property(self, feature: dict[str, Any], field: str,
                        value: Any) -> dict[str, Any]:
        from core.vector_processing import update_feature_property
        return update_feature_property(feature, field, value)

    def add_field(self, features: list[dict[str, Any]], field: str,
                  default: Any = "") -> list[dict[str, Any]]:
        from core.vector_processing import add_property_field
        return add_property_field(features, field, default)

    def delete_field(self, features: list[dict[str, Any]],
                     field: str) -> list[dict[str, Any]]:
        from core.vector_processing import delete_property_field
        return delete_property_field(features, field)
