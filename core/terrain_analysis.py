"""Terrain / DEM analysis: slope, aspect, hillshade, viewshed, contour."""

from __future__ import annotations

from typing import Optional

import numpy as np

from common.logger import logger


def slope(dem: np.ndarray, cell_size: float = 1.0) -> np.ndarray:
    """Slope in degrees using Horn (1981) method.

    Args:
        dem: 2D elevation array (rows, cols).
        cell_size: pixel size in CRS units.
    Returns:
        2D slope array in degrees (0-90).
    """
    dzdx = np.gradient(dem, cell_size, axis=1)
    dzdy = np.gradient(dem, cell_size, axis=0)
    rise = np.sqrt(dzdx**2 + dzdy**2)
    return np.degrees(np.arctan(rise))


def aspect(dem: np.ndarray, cell_size: float = 1.0) -> np.ndarray:
    """Aspect in degrees (0-360, clockwise from north, 0=flat).

    Args:
        dem: 2D elevation array.
        cell_size: pixel size.
    Returns:
        2D aspect array. Flat areas return -1.
    """
    dzdx = np.gradient(dem, cell_size, axis=1)
    dzdy = np.gradient(dem, cell_size, axis=0)
    aspect_rad = np.arctan2(-dzdx, dzdy)
    aspect_deg = np.degrees(aspect_rad)
    aspect_deg = np.where(aspect_deg < 0, aspect_deg + 360, aspect_deg)

    rise = np.sqrt(dzdx**2 + dzdy**2)
    aspect_deg[rise < 1e-9] = -1
    return aspect_deg


def hillshade(
    dem: np.ndarray,
    azimuth: float = 315.0,
    altitude: float = 45.0,
    cell_size: float = 1.0,
    z_factor: float = 1.0,
) -> np.ndarray:
    """Analytical hillshade (0-1 range, float32).

    Args:
        dem: 2D elevation.
        azimuth: sun direction in degrees (0=north, clockwise).
        altitude: sun altitude in degrees above horizon.
        cell_size: pixel size.
        z_factor: vertical exaggeration.
    Returns:
        2D hillshade array (0=shadow, 1=sun-facing).
    """
    dzdx = np.gradient(dem * z_factor, cell_size, axis=1)
    dzdy = np.gradient(dem * z_factor, cell_size, axis=0)

    az_rad = np.radians(360 - azimuth + 90)
    alt_rad = np.radians(altitude)
    sx = np.cos(alt_rad) * np.cos(az_rad)
    sy = np.cos(alt_rad) * np.sin(az_rad)
    sz = np.sin(alt_rad)

    slope_len = np.sqrt(dzdx**2 + dzdy**2 + 1)
    nx, ny, nz = -dzdx / slope_len, -dzdy / slope_len, 1 / slope_len

    shade = sx * nx + sy * ny + sz * nz
    shade = np.clip(shade, 0.0, 1.0)
    return shade.astype(np.float32)


def viewshed(
    dem: np.ndarray,
    observer_row: int,
    observer_col: int,
    observer_height: float = 2.0,
    cell_size: float = 1.0,
    max_radius: Optional[float] = None,
) -> np.ndarray:
    """Binary viewshed using radial line-of-sight method.

    Args:
        dem: 2D elevation.
        observer_row, observer_col: observer position (row, col).
        observer_height: observer height above ground.
        cell_size: ground resolution.
        max_radius: optional max search radius in CRS units.
    Returns:
        Binary 2D array (1=visible, 0=not visible).
    """
    rows, cols = dem.shape
    visible = np.zeros_like(dem, dtype=np.uint8)
    observer_z = float(dem[observer_row, observer_col]) + observer_height

    max_dist = max_radius / cell_size if max_radius else max(rows, cols)
    max_dist = min(max_dist, max(rows, cols))

    for r in range(rows):
        for c in range(cols):
            dr, dc = r - observer_row, c - observer_col
            dst = np.sqrt(dr**2 + dc**2)
            if dst == 0 or dst > max_dist:
                visible[r, c] = 1 if dst == 0 else 0
                continue

            steps = int(np.ceil(dst))
            line_r = np.linspace(observer_row, r, steps + 1).astype(np.float64)
            line_c = np.linspace(observer_col, c, steps + 1).astype(np.float64)
            line_z = np.zeros(steps + 1, dtype=np.float64)

            for i in range(steps + 1):
                rr = int(round(np.clip(line_r[i], 0, rows - 1)))
                cc = int(round(np.clip(line_c[i], 0, cols - 1)))
                line_z[i] = float(dem[rr, cc])

            vis = True
            for i in range(1, steps + 1):
                t = i / steps
                sight_z = observer_z + t * (line_z[-1] - observer_z)
                if line_z[i] > sight_z:
                    vis = False
                    break
            visible[r, c] = 1 if vis else 0

    return visible


def contour(dem: np.ndarray, interval: float = 10.0, cell_size: float = 1.0) -> list[np.ndarray]:
    """Extract contour lines at specified elevation interval.

    Returns list of (N,2) arrays, each being a contour polyline in CRS coordinates.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib required for contour extraction")
        return []

    z_min = float(np.nanmin(dem))
    z_max = float(np.nanmax(dem))
    levels = np.arange(
        np.ceil(z_min / interval) * interval,
        np.floor(z_max / interval) * interval + interval,
        interval,
    )

    rows, cols = dem.shape
    y_coords = np.arange(rows) * cell_size
    x_coords = np.arange(cols) * cell_size
    xx, yy = np.meshgrid(x_coords, y_coords)

    fig, ax = plt.subplots(figsize=(1, 1))
    cs = ax.contour(xx, yy, dem, levels=levels)
    plt.close(fig)

    contours = []
    for collection in cs.collections:
        for path in collection.get_paths():
            verts = path.vertices
            if len(verts) >= 2:
                contours.append(verts.astype(np.float32))
    return contours


def roughness(dem: np.ndarray, window_size: int = 3) -> np.ndarray:
    """Local terrain roughness (std within moving window)."""
    from scipy.ndimage import uniform_filter

    mean = uniform_filter(dem, size=window_size)
    sq_mean = uniform_filter(dem**2, size=window_size)
    return np.sqrt(np.maximum(sq_mean - mean**2, 0))


def curvature(dem: np.ndarray, cell_size: float = 1.0) -> np.ndarray:
    """Profile curvature (2nd derivative along slope direction)."""
    dzdx = np.gradient(dem, cell_size, axis=1)
    dzdy = np.gradient(dem, cell_size, axis=0)
    d2zdx2 = np.gradient(dzdx, cell_size, axis=1)
    d2zdy2 = np.gradient(dzdy, cell_size, axis=0)
    dzdxdy = np.gradient(dzdx, cell_size, axis=0)
    p = dzdx**2 + dzdy**2
    numer = d2zdx2 * dzdx**2 + 2 * dzdxdy * dzdx * dzdy + d2zdy2 * dzdy**2
    p_safe = np.where(p < 1e-9, 1e-9, p)
    curv = -numer / (p_safe * np.sqrt(1 + p) ** 3)
    return curv
