"""Raster data contracts -- pure domain models with no I/O dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GeoTransform:
    """GDAL-style 6-element affine geotransform.

    Pixel-to-map:  X_geo = x0 + px * dx + py * rx
                   Y_geo = y0 + px * ry + py * dy
    """

    x0: float = 0.0
    dx: float = 1.0
    rx: float = 0.0
    y0: float = 0.0
    ry: float = 0.0
    dy: float = -1.0

    def to_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.x0, self.dx, self.rx, self.y0, self.ry, self.dy)

    @classmethod
    def from_tuple(cls, t: tuple[float, ...]) -> GeoTransform:
        if len(t) >= 6:
            return cls(t[0], t[1], t[2], t[3], t[4], t[5])
        return cls()

    def to_dict(self) -> dict:
        return {
            "x0": self.x0, "dx": self.dx, "rx": self.rx,
            "y0": self.y0, "ry": self.ry, "dy": self.dy,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GeoTransform:
        return cls(
            x0=d.get("x0", 0.0), dx=d.get("dx", 1.0), rx=d.get("rx", 0.0),
            y0=d.get("y0", 0.0), ry=d.get("ry", 0.0), dy=d.get("dy", -1.0),
        )


@dataclass
class SpatialReference:
    """Coordinate reference system descriptor -- CRS identity only.

    Carries only CRS identity fields. Bounds, transform, and raster dimensions
    belong on RasterMetadata to avoid the god-object problem.
    """

    crs: str = ""
    epsg: Optional[int] = None
    wkt: str = ""
    authority: str = ""

    @property
    def has_crs(self) -> bool:
        return bool(self.crs or self.epsg or self.wkt)

    def to_dict(self) -> dict:
        return {
            "crs": self.crs, "epsg": self.epsg,
            "wkt": self.wkt, "authority": self.authority,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SpatialReference:
        return cls(
            crs=d.get("crs", ""), epsg=d.get("epsg"),
            wkt=d.get("wkt", ""), authority=d.get("authority", ""),
        )


@dataclass
class RasterBand:
    """Metadata for a single raster band."""

    index: int = 1
    data_type: str = ""
    nodata: Optional[float] = None
    description: str = ""
    stats_min: Optional[float] = None
    stats_max: Optional[float] = None
    color_interpretation: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index, "data_type": self.data_type,
            "nodata": self.nodata, "description": self.description,
            "stats_min": self.stats_min, "stats_max": self.stats_max,
            "color_interpretation": self.color_interpretation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RasterBand:
        return cls(
            index=d.get("index", 1), data_type=d.get("data_type", ""),
            nodata=d.get("nodata"), description=d.get("description", ""),
            stats_min=d.get("stats_min"), stats_max=d.get("stats_max"),
            color_interpretation=d.get("color_interpretation", ""),
        )


@dataclass
class RasterMetadata:
    """Portal from a raster file on disk -- everything except pixel data."""

    width: int = 0
    height: int = 0
    bands: int = 0
    dtype: str = ""
    driver: str = ""
    geo_transform: Optional[GeoTransform] = None
    spatial_ref: Optional[SpatialReference] = None
    bounds: Optional[tuple[float, float, float, float]] = None
    pixel_size: Optional[tuple[float, float]] = None
    file_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "bands": self.bands, "dtype": self.dtype,
            "driver": self.driver,
            "geo_transform": self.geo_transform.to_dict() if self.geo_transform else None,
            "spatial_ref": self.spatial_ref.to_dict() if self.spatial_ref else None,
            "bounds": list(self.bounds) if self.bounds else None,
            "pixel_size": list(self.pixel_size) if self.pixel_size else None,
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RasterMetadata:
        gt = d.get("geo_transform")
        sr = d.get("spatial_ref")
        bounds = d.get("bounds")
        ps = d.get("pixel_size")
        return cls(
            width=d.get("width", 0), height=d.get("height", 0),
            bands=d.get("bands", 0), dtype=d.get("dtype", ""),
            driver=d.get("driver", ""),
            geo_transform=GeoTransform.from_dict(gt) if isinstance(gt, dict) else None,
            spatial_ref=SpatialReference.from_dict(sr) if isinstance(sr, dict) else None,
            bounds=tuple(bounds) if bounds else None,
            pixel_size=tuple(ps) if ps else None,
            file_hash=d.get("file_hash", ""),
        )


@dataclass
class RasterDataset:
    """Full raster handle -- path, metadata, and optional band definitions."""

    path: str = ""
    metadata: RasterMetadata = field(default_factory=RasterMetadata)
    bands: list[RasterBand] = field(default_factory=list)

    @property
    def name(self) -> str:
        from pathlib import Path
        return Path(self.path).name

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "metadata": self.metadata.to_dict(),
            "bands": [b.to_dict() for b in self.bands],
        }

    @classmethod
    def from_dict(cls, d: dict) -> RasterDataset:
        return cls(
            path=d.get("path", ""),
            metadata=RasterMetadata.from_dict(d.get("metadata", {})),
            bands=[RasterBand.from_dict(b) for b in d.get("bands", [])],
        )
