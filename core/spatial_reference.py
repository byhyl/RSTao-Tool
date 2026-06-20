"""Spatial reference and data-source audit helpers."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from common.logger import logger


@dataclass
class SpatialReference:
    """Portable spatial reference summary for project metadata and reports."""

    source_path: str = ""
    source_type: str = ""
    crs: str = ""
    epsg: Optional[int] = None
    wkt: str = ""
    bounds: Optional[tuple[float, float, float, float]] = None
    transform: Optional[tuple[float, ...]] = None
    pixel_size: Optional[tuple[float, float]] = None
    width: int = 0
    height: int = 0
    bands: int = 0
    dtype: str = ""
    nodata: Any = None
    file_hash: str = ""
    warning: str = ""

    @property
    def has_crs(self) -> bool:
        return bool(self.crs or self.epsg or self.wkt)

    def to_dict(self) -> dict:
        return asdict(self)


def read_raster_spatial_ref(path: str | Path) -> SpatialReference:
    """Read CRS, transform, bounds, and lightweight raster metadata."""
    raster_path = Path(path)
    ref = SpatialReference(
        source_path=str(raster_path),
        source_type="raster",
        file_hash=compute_file_hash(raster_path),
    )

    try:
        import rasterio

        with rasterio.open(raster_path) as ds:
            ref.width = int(ds.width)
            ref.height = int(ds.height)
            ref.bands = int(ds.count)
            ref.dtype = ds.dtypes[0] if ds.dtypes else ""
            ref.crs = str(ds.crs) if ds.crs else ""
            ref.epsg = ds.crs.to_epsg() if ds.crs else None
            ref.wkt = ds.crs.to_wkt() if ds.crs else ""
            ref.bounds = tuple(float(v) for v in ds.bounds)
            ref.transform = rasterio_transform_to_viewer(ds.transform)
            ref.pixel_size = (abs(float(ds.transform.a)), abs(float(ds.transform.e)))
            ref.nodata = ds.nodata
            if not ref.has_crs:
                ref.warning = "Raster has no CRS."
            return ref
    except ImportError:
        logger.debug("rasterio is not installed; falling back to image metadata.")
    except Exception as exc:
        logger.debug(f"Failed to read raster spatial reference: {exc}")

    try:
        from data.image_io import get_image_metadata

        meta = get_image_metadata(raster_path)
        ref.width = int(meta.get("width") or 0)
        ref.height = int(meta.get("height") or 0)
        ref.bands = int(meta.get("bands") or 0)
        ref.dtype = str(meta.get("dtype") or "")
        ref.crs = str(meta.get("crs") or "")
        ref.epsg = meta.get("epsg")
        ref.bounds = meta.get("bounds")
        ref.pixel_size = meta.get("pixel_size")
    except Exception as exc:
        ref.warning = f"Failed to read spatial reference: {exc}"

    if not ref.has_crs:
        ref.warning = ref.warning or "Raster has no CRS."
    return ref


def read_vector_spatial_ref(path: str | Path) -> SpatialReference:
    """Read CRS and bounds for vector data."""
    vector_path = Path(path)
    ref = SpatialReference(
        source_path=str(vector_path),
        source_type="vector",
        file_hash=compute_file_hash(vector_path),
    )
    try:
        import fiona

        with fiona.open(vector_path, "r", encoding="utf-8") as src:
            ref.crs = str(src.crs or "")
            ref.epsg = _epsg_from_crs(src.crs)
            ref.wkt = src.crs_wkt or ""
            ref.bounds = tuple(float(v) for v in src.bounds) if src.bounds else None
            ref.bands = 0
            ref.width = len(src)
            ref.dtype = (src.schema or {}).get("geometry", "")
    except Exception as exc:
        ref.warning = f"Failed to read vector spatial reference: {exc}"
    if not ref.has_crs:
        ref.warning = ref.warning or "Vector has no CRS."
    return ref


def compare_spatial_refs(
    a: SpatialReference | dict | None, b: SpatialReference | dict | None
) -> dict:
    """Compare two spatial references and return a user-facing status."""
    ref_a = ensure_spatial_ref(a)
    ref_b = ensure_spatial_ref(b)
    if not ref_a or not ref_b:
        return {
            "compatible": True,
            "level": "unknown",
            "message": "Not enough spatial reference information to compare.",
        }
    if not ref_a.has_crs or not ref_b.has_crs:
        return {
            "compatible": True,
            "level": "warning",
            "message": "At least one data source has no CRS.",
        }
    if ref_a.epsg and ref_b.epsg:
        compatible = ref_a.epsg == ref_b.epsg
        return {
            "compatible": compatible,
            "level": "ok" if compatible else "error",
            "message": (
                "CRS matches."
                if compatible
                else f"CRS mismatch: EPSG:{ref_a.epsg} vs EPSG:{ref_b.epsg}."
            ),
        }
    compatible = (ref_a.crs or ref_a.wkt) == (ref_b.crs or ref_b.wkt)
    return {
        "compatible": compatible,
        "level": "ok" if compatible else "warning",
        "message": "CRS description matches." if compatible else "CRS descriptions differ.",
    }


def ensure_spatial_ref(value: SpatialReference | dict | None) -> Optional[SpatialReference]:
    if value is None:
        return None
    if isinstance(value, SpatialReference):
        return value
    allowed = SpatialReference().__dict__.keys()
    payload = {key: value.get(key) for key in allowed if key in value}
    return SpatialReference(**payload)


def format_spatial_ref(ref: SpatialReference | dict | None) -> str:
    spatial_ref = ensure_spatial_ref(ref)
    if not spatial_ref:
        return "No spatial reference"
    parts = []
    if spatial_ref.epsg:
        parts.append(f"EPSG:{spatial_ref.epsg}")
    elif spatial_ref.crs:
        parts.append(spatial_ref.crs)
    else:
        parts.append("CRS unknown")
    if spatial_ref.bounds:
        parts.append("Bounds " + ", ".join(f"{v:.3f}" for v in spatial_ref.bounds))
    if spatial_ref.pixel_size:
        parts.append(f"Pixel {spatial_ref.pixel_size[0]:.6g} x {spatial_ref.pixel_size[1]:.6g}")
    if spatial_ref.warning:
        parts.append(spatial_ref.warning)
    return " | ".join(parts)


def rasterio_transform_to_viewer(transform) -> tuple[float, float, float, float, float, float]:
    """Convert rasterio Affine to GDAL/viewer order: x0, dx, rx, y0, ry, dy."""
    return (
        float(transform.c),
        float(transform.a),
        float(transform.b),
        float(transform.f),
        float(transform.d),
        float(transform.e),
    )


def normalize_geo_transform(
    transform: Any,
) -> Optional[tuple[float, float, float, float, float, float]]:
    """Normalize common transform values to GDAL/viewer order."""
    if transform is None:
        return None
    if hasattr(transform, "a") and hasattr(transform, "c"):
        return rasterio_transform_to_viewer(transform)
    try:
        values = tuple(float(v) for v in transform)
    except TypeError:
        return None
    if len(values) >= 9:
        a, b, c, d, e, f = values[:6]
        return (c, a, b, f, d, e)
    if len(values) >= 6:
        return values[:6]
    return None


def pixel_to_map(px: float, py: float, transform: Any) -> Optional[tuple[float, float]]:
    """Convert pixel coordinates to map coordinates using a GDAL-style transform."""
    geo = normalize_geo_transform(transform)
    if not geo:
        return None
    x0, dx, rx, y0, ry, dy = geo
    return (x0 + px * dx + py * rx, y0 + px * ry + py * dy)


def map_to_pixel(mx: float, my: float, transform: Any) -> Optional[tuple[float, float]]:
    """Convert map coordinates back to pixel coordinates."""
    geo = normalize_geo_transform(transform)
    if not geo:
        return None
    x0, dx, rx, y0, ry, dy = geo
    det = dx * dy - rx * ry
    if abs(det) < 1e-12:
        return None
    x = mx - x0
    y = my - y0
    px = (dy * x - rx * y) / det
    py = (-ry * x + dx * y) / det
    return (px, py)


def compute_file_hash(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA256 hash prefix for audit trails."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _epsg_from_crs(crs: Any) -> Optional[int]:
    if not crs:
        return None
    try:
        return crs.to_epsg()
    except AttributeError:
        pass
    try:
        from pyproj import CRS

        return CRS.from_user_input(crs).to_epsg()
    except Exception:
        return None
