"""Raster geospatial operations.  Thin wrapper; will expand later."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.logger import logger
from core.spatial_reference import read_raster_spatial_ref

if TYPE_CHECKING:
    from .app_context import AppContext


class RasterService:
    """Raster operations service."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    def spatial_ref(self, path: str):
        """Read full spatial reference for a raster file."""
        try:
            return read_raster_spatial_ref(path)
        except Exception as exc:
            logger.debug("读取栅格空间参考失败 %s: %s", path, exc)
            return None

    def geo_transform(self, path: str):
        """Return GDAL-style geotransform tuple, or None."""
        ref = self.spatial_ref(path)
        return ref.transform if ref else None
