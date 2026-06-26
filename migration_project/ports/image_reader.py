"""Abstract interface for reading raster/image data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from migration_project.domain.raster import RasterMetadata


class ImageReader(ABC):
    """Port for reading image and raster data from disk.

    Maps to: data/image_io.py (read_image, read_raster_data, get_image_metadata)
    """

    @abstractmethod
    def read_image(self, path: str) -> Any:
        """Read an image file and return pixel data.

        Returns: np.ndarray (H, W, C) in RGB format.
        """
        ...

    @abstractmethod
    def read_metadata(self, path: str) -> RasterMetadata:
        """Read raster metadata without loading full pixel data."""
        ...

    @abstractmethod
    def read_raster_data(
        self, path: str, bands: Optional[list[int]] = None, preserve_dtype: bool = True
    ) -> Any:
        """Read raster pixel data for processing.

        Args:
            path: File path to the raster.
            bands: List of 1-based band indices to read (None = all bands).
            preserve_dtype: If True, return raw dtype; if False, return uint8 preview.

        Returns: np.ndarray.
        """
        ...

    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Return list of supported file extensions (e.g. ['.tif', '.png'])."""
        ...
