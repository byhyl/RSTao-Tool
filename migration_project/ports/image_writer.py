"""Abstract interface for writing image/raster data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ImageWriter(ABC):
    """Port for writing image and raster data to disk.

    Maps to: data/image_io.py (save_image, save_geotiff_like, save_raster_result)
    """

    @abstractmethod
    def save_image(self, path: str, data: Any) -> bool:
        """Save an image to disk. Returns True on success.

        Args:
            path: Output file path.
            data: np.ndarray (H, W) or (H, W, C).
        """
        ...

    @abstractmethod
    def save_geotiff(
        self, src_path: str, data: Any, dst_path: str, color_order: str = "BGR"
    ) -> bool:
        """Save a GeoTIFF preserving georeference from src_path.

        Args:
            src_path: Source GeoTIFF to copy georeference from.
            data: np.ndarray to write.
            dst_path: Output file path.
            color_order: "BGR" or "RGB".
        """
        ...

    @abstractmethod
    def save_raster_result(
        self, src_path: str, data: Any, dst_path: str, color_order: str = "RGB"
    ) -> bool:
        """Auto-detect output format and save raster processing result.

        Uses GeoTIFF path when src/dst are both geospatial, regular image otherwise.
        """
        ...
