"""Vector data contracts -- GeoJSON-inspired geometry model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class GeometryType(Enum):
    POINT = "Point"
    LINE_STRING = "LineString"
    POLYGON = "Polygon"
    MULTI_POINT = "MultiPoint"
    MULTI_LINE_STRING = "MultiLineString"
    MULTI_POLYGON = "MultiPolygon"
    GEOMETRY_COLLECTION = "GeometryCollection"


@dataclass
class VectorGeometry:
    """GeoJSON-compatible geometry object.

    Coordinates follow GeoJSON conventions:
      Point: [x, y]
      LineString: [[x1,y1], [x2,y2], ...]
      Polygon: [[[x1,y1], ...]]  (outer ring, then inner rings)
    """

    type: GeometryType = GeometryType.POINT
    coordinates: Any = field(default_factory=list)
    srid: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "coordinates": self.coordinates,
            "srid": self.srid,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VectorGeometry:
        geom_type = d.get("type", "Point")
        if isinstance(geom_type, str):
            try:
                gt = GeometryType(geom_type)
            except ValueError:
                gt = GeometryType.POINT
        else:
            gt = GeometryType.POINT
        return cls(type=gt, coordinates=d.get("coordinates", []), srid=d.get("srid"))


@dataclass
class VectorFeature:
    """A single feature with geometry and properties."""

    id: str = ""
    geometry: VectorGeometry = field(default_factory=VectorGeometry)
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "geometry": self.geometry.to_dict(),
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VectorFeature:
        return cls(
            id=d.get("id", ""),
            geometry=VectorGeometry.from_dict(d.get("geometry", {})),
            properties=d.get("properties", {}),
        )


@dataclass
class VectorMetadata:
    """Vector layer metadata -- schema and spatial reference."""

    feature_count: int = 0
    geometry_type: GeometryType = GeometryType.POINT
    crs: str = ""
    epsg: Optional[int] = None
    bounds: Optional[tuple[float, float, float, float]] = None
    schema: dict[str, str] = field(default_factory=dict)
    driver: str = ""
    encoding: str = "utf-8"

    def to_dict(self) -> dict:
        return {
            "feature_count": self.feature_count,
            "geometry_type": self.geometry_type.value,
            "crs": self.crs, "epsg": self.epsg,
            "bounds": list(self.bounds) if self.bounds else None,
            "schema": self.schema, "driver": self.driver,
            "encoding": self.encoding,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VectorMetadata:
        gt_raw = d.get("geometry_type", "Point")
        if isinstance(gt_raw, str):
            try:
                geom_type = GeometryType(gt_raw)
            except ValueError:
                geom_type = GeometryType.POINT
        else:
            geom_type = GeometryType.POINT
        bounds = d.get("bounds")
        return cls(
            feature_count=d.get("feature_count", 0),
            geometry_type=geom_type,
            crs=d.get("crs", ""), epsg=d.get("epsg"),
            bounds=tuple(bounds) if bounds else None,
            schema=d.get("schema", {}), driver=d.get("driver", ""),
            encoding=d.get("encoding", "utf-8"),
        )


@dataclass
class VectorDataset:
    """A complete vector dataset -- path, metadata, and features."""

    path: str = ""
    metadata: VectorMetadata = field(default_factory=VectorMetadata)
    features: list[VectorFeature] = field(default_factory=list)

    @property
    def name(self) -> str:
        from pathlib import Path
        return Path(self.path).stem

    @property
    def feature_count(self) -> int:
        return len(self.features)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "metadata": self.metadata.to_dict(),
            "features": [f.to_dict() for f in self.features],
        }

    @classmethod
    def from_dict(cls, d: dict) -> VectorDataset:
        return cls(
            path=d.get("path", ""),
            metadata=VectorMetadata.from_dict(d.get("metadata", {})),
            features=[VectorFeature.from_dict(f) for f in d.get("features", [])],
        )
