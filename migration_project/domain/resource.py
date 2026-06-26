"""Unified resource record and catalog domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ResourceKind(Enum):
    RASTER = "raster"
    VECTOR = "vector"
    POINT_CLOUD = "pointcloud"
    MESH = "mesh"
    MODEL = "model"
    FILE = "file"


@dataclass
class Resource:
    """Unified resource record -- one per file/data-source imported into a project."""

    id: str = ""
    name: str = ""
    source_path: str = ""
    kind: ResourceKind = ResourceKind.FILE
    extension: str = ""
    size_bytes: int = 0
    file_hash: str = ""
    visible: bool = True
    opacity: float = 1.0
    locked: bool = False
    order: int = 0
    crs: str = ""
    epsg: Optional[int] = None
    bounds: Optional[tuple[float, ...]] = None
    width: int = 0
    height: int = 0
    bands: int = 0
    dtype: str = ""
    point_count: int = 0
    vertex_count: int = 0
    face_count: int = 0
    dimensions: int = 0
    format_detail: str = ""
    warning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "source_path": self.source_path, "kind": self.kind.value,
            "extension": self.extension, "size_bytes": self.size_bytes,
            "file_hash": self.file_hash, "visible": self.visible,
            "opacity": self.opacity, "locked": self.locked,
            "order": self.order, "crs": self.crs, "epsg": self.epsg,
            "bounds": list(self.bounds) if self.bounds else None,
            "width": self.width, "height": self.height,
            "bands": self.bands, "dtype": self.dtype,
            "point_count": self.point_count, "vertex_count": self.vertex_count,
            "face_count": self.face_count, "dimensions": self.dimensions,
            "format_detail": self.format_detail, "warning": self.warning,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Resource:
        kind_raw = d.get("kind", "file")
        if isinstance(kind_raw, str):
            try:
                kind = ResourceKind(kind_raw)
            except ValueError:
                kind = ResourceKind.FILE
        else:
            kind = ResourceKind.FILE
        bounds = d.get("bounds")
        return cls(
            id=d.get("id", ""), name=d.get("name", ""),
            source_path=d.get("source_path", ""), kind=kind,
            extension=d.get("extension", ""), size_bytes=d.get("size_bytes", 0),
            file_hash=d.get("file_hash", ""), visible=d.get("visible", True),
            opacity=d.get("opacity", 1.0), locked=d.get("locked", False),
            order=d.get("order", 0), crs=d.get("crs", ""),
            epsg=d.get("epsg"), bounds=tuple(bounds) if bounds else None,
            width=d.get("width", 0), height=d.get("height", 0),
            bands=d.get("bands", 0), dtype=d.get("dtype", ""),
            point_count=d.get("point_count", 0), vertex_count=d.get("vertex_count", 0),
            face_count=d.get("face_count", 0), dimensions=d.get("dimensions", 0),
            format_detail=d.get("format_detail", ""), warning=d.get("warning", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class ResourceCatalog:
    """A collection of resources with pagination support."""

    resources: list[Resource] = field(default_factory=list)
    total_count: int = 0

    def to_dict(self) -> dict:
        return {
            "resources": [r.to_dict() for r in self.resources],
            "total_count": self.total_count or len(self.resources),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ResourceCatalog:
        resources = [Resource.from_dict(r) for r in d.get("resources", [])]
        return cls(resources=resources, total_count=d.get("total_count", len(resources)))
