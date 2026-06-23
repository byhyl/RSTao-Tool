"""Point cloud I/O: LAS/LAZ export with classification and RGB support."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from common.logger import logger


def _coerce_crs(crs_text: str):
    """Return a pyproj CRS from WKT/EPSG text when available."""
    if not crs_text:
        return None
    try:
        from pyproj import CRS

        return CRS.from_user_input(crs_text)
    except Exception as exc:
        logger.debug("Could not parse CRS for LAS export: %s", exc)
        return None


def export_las(
    points: np.ndarray,
    path: str | Path,
    classifications: Optional[np.ndarray] = None,
    colors: Optional[np.ndarray] = None,
    intensities: Optional[np.ndarray] = None,
    return_numbers: Optional[np.ndarray] = None,
    crs_wkt: str = "",
    scale: tuple[float, float, float] = (0.001, 0.001, 0.001),
) -> bool:
    """Export point cloud to LAS/LAZ file with optional classification and RGB.

    Args:
        points: (N, 3) float64 array in CRS coordinates.
        path: Output .las or .laz path.
        classifications: (N,) uint8 classification codes.
        colors: (N, 3) uint8 or float32 (0-1) RGB colors.
        intensities: (N,) uint16 intensity values.
        return_numbers: (N,) uint8 return numbers.
        crs_wkt: WKT/EPSG/user-input string for coordinate reference system.
        scale: XYZ scale factors (LAS stores integer coords).
    Returns:
        True on success.
    """
    try:
        import laspy
    except ImportError:
        logger.error("laspy not installed; cannot export LAS")
        return False

    try:
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] < 3 or len(points) == 0:
            raise ValueError("points must be a non-empty (N, 3) array")
        n = len(points)
        header = laspy.LasHeader(point_format=3, version="1.2")
        header.offsets = np.min(points, axis=0)
        header.scales = np.array(scale, dtype=np.float64)
        crs = _coerce_crs(crs_wkt)
        if crs is not None:
            try:
                header.add_crs(crs)
            except Exception as exc:
                logger.debug("Could not embed CRS in LAS header: %s", exc)

        las = laspy.LasData(header)
        las.x = points[:, 0]
        las.y = points[:, 1]
        las.z = points[:, 2]

        if classifications is not None and len(classifications) == n:
            las.classification = classifications.astype(np.uint8)
        else:
            las.classification = np.zeros(n, dtype=np.uint8)

        if intensities is not None and len(intensities) == n:
            las.intensity = intensities.astype(np.uint16)

        if return_numbers is not None and len(return_numbers) == n:
            las.return_number = return_numbers.astype(np.uint8)

        if colors is not None and len(colors) == n:
            c = np.nan_to_num(np.asarray(colors, dtype=np.float64))
            if c.ndim == 1:
                c = np.column_stack([c, c, c])
            if c.max(initial=0) <= 1.0:
                c = (c * 65535).astype(np.uint16)
            else:
                c = np.clip(c, 0, 65535).astype(np.uint16)
            las.red = c[:, 0]
            las.green = c[:, 1]
            las.blue = c[:, 2]

        las.write(str(path))
        logger.info(f"Exported LAS: {n} points -> {path}")
        return True

    except Exception as exc:
        logger.error(f"LAS export failed: {exc}", exc_info=True)
        return False


def export_ply(
    points: np.ndarray,
    path: str | Path,
    colors: Optional[np.ndarray] = None,
    normals: Optional[np.ndarray] = None,
) -> bool:
    """Export point cloud to ASCII PLY file."""
    try:
        n = len(points)
        with open(path, "w", encoding="utf-8") as f:
            f.write("ply\nformat ascii 1.0\n")
            f.write(f"element vertex {n}\n")
            f.write("property float x\nproperty float y\nproperty float z\n")
            has_color = colors is not None and len(colors) == n
            has_normal = normals is not None and len(normals) == n
            if has_color:
                f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
            if has_normal:
                f.write("property float nx\nproperty float ny\nproperty float nz\n")
            f.write("end_header\n")

            c_arr = None
            if has_color:
                c_arr = np.asarray(colors, dtype=np.float64)
                if c_arr.max() <= 1.0:
                    c_arr = (c_arr * 255).astype(np.uint8)

            for i in range(n):
                line = f"{points[i,0]:.6f} {points[i,1]:.6f} {points[i,2]:.6f}"
                if c_arr is not None:
                    line += f" {c_arr[i,0]} {c_arr[i,1]} {c_arr[i,2]}"
                if has_normal:
                    line += f" {normals[i,0]:.6f} {normals[i,1]:.6f} {normals[i,2]:.6f}"
                f.write(line + "\n")
        logger.info(f"Exported PLY: {n} points -> {path}")
        return True
    except Exception as exc:
        logger.error(f"PLY export failed: {exc}", exc_info=True)
        return False


def export_xyz(points: np.ndarray, path: str | Path, delimiter: str = " ") -> bool:
    """Export point cloud to XYZ text file."""
    try:
        np.savetxt(str(path), points, fmt="%.6f", delimiter=delimiter)
        logger.info(f"Exported XYZ: {len(points)} points -> {path}")
        return True
    except Exception as exc:
        logger.error(f"XYZ export failed: {exc}", exc_info=True)
        return False
