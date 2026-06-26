"""Point cloud data contracts -- pure domain fields without numpy dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PointCloudMetadata:
    """Metadata describing a point cloud file on disk."""

    point_count: int = 0
    dimensions: int = 3
    has_colors: bool = False
    has_classifications: bool = False
    has_intensity: bool = False
    has_normals: bool = False
    bounds: Optional[tuple[float, ...]] = None
    crs: str = ""
    epsg: Optional[int] = None
    driver: str = ""
    format_detail: str = ""
    warning: str = ""

    def to_dict(self) -> dict:
        return {
            "point_count": self.point_count, "dimensions": self.dimensions,
            "has_colors": self.has_colors, "has_classifications": self.has_classifications,
            "has_intensity": self.has_intensity, "has_normals": self.has_normals,
            "bounds": list(self.bounds) if self.bounds else None,
            "crs": self.crs, "epsg": self.epsg,
            "driver": self.driver, "format_detail": self.format_detail,
            "warning": self.warning,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PointCloudMetadata:
        bounds = d.get("bounds")
        return cls(
            point_count=d.get("point_count", 0), dimensions=d.get("dimensions", 3),
            has_colors=d.get("has_colors", False),
            has_classifications=d.get("has_classifications", False),
            has_intensity=d.get("has_intensity", False),
            has_normals=d.get("has_normals", False),
            bounds=tuple(bounds) if bounds else None,
            crs=d.get("crs", ""), epsg=d.get("epsg"),
            driver=d.get("driver", ""), format_detail=d.get("format_detail", ""),
            warning=d.get("warning", ""),
        )


@dataclass
class PointCloudData:
    """Point cloud data descriptor -- field definitions only.

    Describes structure (what attributes exist) without carrying numpy arrays.
    The implementation layer handles actual np.ndarray data.
    """

    point_count: int = 0
    dimensions: int = 3
    has_colors: bool = False
    has_classifications: bool = False
    has_intensity: bool = False
    has_normals: bool = False
    dtype: str = "float32"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "point_count": self.point_count, "dimensions": self.dimensions,
            "has_colors": self.has_colors,
            "has_classifications": self.has_classifications,
            "has_intensity": self.has_intensity,
            "has_normals": self.has_normals, "dtype": self.dtype,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PointCloudData:
        return cls(
            point_count=d.get("point_count", 0), dimensions=d.get("dimensions", 3),
            has_colors=d.get("has_colors", False),
            has_classifications=d.get("has_classifications", False),
            has_intensity=d.get("has_intensity", False),
            has_normals=d.get("has_normals", False),
            dtype=d.get("dtype", "float32"), metadata=d.get("metadata", {}),
        )


@dataclass
class PointCloudDataset:
    """A complete point cloud dataset reference -- path + metadata."""

    path: str = ""
    metadata: PointCloudMetadata = field(default_factory=PointCloudMetadata)

    @property
    def name(self) -> str:
        from pathlib import Path
        return Path(self.path).name

    def to_dict(self) -> dict:
        return {"path": self.path, "metadata": self.metadata.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> PointCloudDataset:
        return cls(
            path=d.get("path", ""),
            metadata=PointCloudMetadata.from_dict(d.get("metadata", {})),
        )
