"""Abstract interface for reading vector data."""

from __future__ import annotations

from abc import ABC, abstractmethod

from migration_project.domain.vector import VectorDataset


class VectorReader(ABC):
    """Port for reading vector data from disk.

    Maps to: data/vector_io.py (read_shp)
    """

    @abstractmethod
    def read(self, path: str) -> VectorDataset:
        """Read a vector file and return a domain VectorDataset.

        Supports: SHP, GeoJSON, GPKG, DXF (and their equivalents).
        """
        ...

    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Return list of supported file extensions (e.g. ['.shp', '.geojson'])."""
        ...
