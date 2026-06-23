"""Point cloud operations: filtering, sampling, classification, registration, volume.

Built on Open3D + numpy. All functions accept and return numpy arrays
or open3d geometry objects so they compose cleanly with the scene graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

import numpy as np

from common.logger import logger
from core.gpu_accel import get_cupy

o3d = None
_O3D_AVAILABLE: bool | None = None


@dataclass
class PointCloudData:
    """Numpy point cloud with optional per-point attributes.

    The UI still renders Open3D/PyVista geometry, but algorithm code should prefer
    this container so filters and sampling keep colors/classifications/intensity.
    """

    points: np.ndarray
    colors: Optional[np.ndarray] = None
    classifications: Optional[np.ndarray] = None
    intensities: Optional[np.ndarray] = None
    normals: Optional[np.ndarray] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        points = np.asarray(self.points, dtype=np.float64)
        if points.size == 0:
            self.points = np.empty((0, 3), dtype=np.float64)
        else:
            points = points.reshape(-1, points.shape[-1])
            if points.shape[1] < 3:
                padded = np.zeros((len(points), 3), dtype=np.float64)
                padded[:, : points.shape[1]] = points
                points = padded
            self.points = points[:, :3]
        n = len(self.points)
        self.colors = _coerce_attr(self.colors, n, 3, np.float64)
        self.classifications = _coerce_attr(self.classifications, n, 1, np.int32, squeeze=True)
        self.intensities = _coerce_attr(self.intensities, n, 1, np.float32, squeeze=True)
        self.normals = _coerce_attr(self.normals, n, 3, np.float64)

    def subset(self, indices: np.ndarray) -> "PointCloudData":
        indices = np.asarray(indices, dtype=np.int64)
        return PointCloudData(
            self.points[indices],
            colors=self.colors[indices] if self.colors is not None else None,
            classifications=(
                self.classifications[indices] if self.classifications is not None else None
            ),
            intensities=self.intensities[indices] if self.intensities is not None else None,
            normals=self.normals[indices] if self.normals is not None else None,
            metadata=dict(self.metadata),
        )

    def copy(self) -> "PointCloudData":
        return PointCloudData(
            self.points.copy(),
            colors=self.colors.copy() if self.colors is not None else None,
            classifications=(
                self.classifications.copy() if self.classifications is not None else None
            ),
            intensities=self.intensities.copy() if self.intensities is not None else None,
            normals=self.normals.copy() if self.normals is not None else None,
            metadata=dict(self.metadata),
        )

    def to_o3d(self):
        return to_o3d_pointcloud(self.points, self.colors, self.normals)

    @classmethod
    def from_o3d(
        cls,
        pcd,
        classifications: Optional[np.ndarray] = None,
        intensities: Optional[np.ndarray] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "PointCloudData":
        points, colors, normals = from_o3d_pointcloud(pcd)
        return cls(
            points,
            colors=colors,
            normals=normals,
            classifications=classifications,
            intensities=intensities,
            metadata=metadata or {},
        )


def _coerce_attr(
    values,
    expected_len: int,
    width: int,
    dtype,
    squeeze: bool = False,
) -> Optional[np.ndarray]:
    if values is None:
        return None
    arr = np.asarray(values, dtype=dtype)
    if squeeze:
        arr = arr.reshape(-1)
        return arr if len(arr) == expected_len else None
    if arr.ndim == 1:
        arr = arr.reshape(-1, width)
    if len(arr) != expected_len:
        return None
    return arr[:, :width]


def _get_o3d():
    """Import Open3D only when a 3D operation actually needs it."""
    global o3d, _O3D_AVAILABLE
    if o3d is not None:
        return o3d
    if _O3D_AVAILABLE is False:
        raise RuntimeError("open3d required")
    try:
        import open3d as _o3d
    except ImportError as exc:
        _O3D_AVAILABLE = False
        logger.warning("open3d not installed; pointcloud_ops limited to numpy fallbacks")
        raise RuntimeError("open3d required") from exc
    o3d = _o3d
    _O3D_AVAILABLE = True
    return o3d


def to_o3d_pointcloud(
    points: np.ndarray, colors: Optional[np.ndarray] = None, normals: Optional[np.ndarray] = None
):
    """Convert (N,3) numpy array to open3d.geometry.PointCloud."""
    _get_o3d()
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64)[:, :3])
    if colors is not None and colors.size:
        pcd.colors = o3d.utility.Vector3dVector(np.asarray(colors, dtype=np.float64)[:, :3])
    if normals is not None and normals.size:
        pcd.normals = o3d.utility.Vector3dVector(np.asarray(normals, dtype=np.float64)[:, :3])
    return pcd


def from_o3d_pointcloud(pcd) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    """Extract points, colors, normals from open3d PointCloud as numpy arrays."""
    pts = np.asarray(pcd.points, dtype=np.float32)
    clr = np.asarray(pcd.colors, dtype=np.float32) if pcd.has_colors() else None
    nrm = np.asarray(pcd.normals, dtype=np.float32) if pcd.has_normals() else None
    return pts, clr, nrm


# ═══════════════ Downsampling ═══════════════


def voxel_downsample(pcd, voxel_size: float = 0.1):
    """Uniform voxel downsampling. Returns open3d PointCloud."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    return pcd.voxel_down_sample(voxel_size)


def uniform_downsample(pcd, every_k_points: int = 5):
    """Keep every k-th point. Returns open3d PointCloud."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    return pcd.uniform_down_sample(every_k_points)


def sample_indices(count: int, max_points: int, mode: str = "linspace") -> np.ndarray:
    """Return deterministic indices for a render/preview point budget."""
    if count <= 0:
        return np.array([], dtype=np.int64)
    if max_points <= 0 or count <= max_points:
        return np.arange(count, dtype=np.int64)
    if mode == "stride":
        step = max(1, int(np.ceil(count / max_points)))
        return np.arange(0, count, step, dtype=np.int64)[:max_points]
    return np.linspace(0, count - 1, max_points, dtype=np.int64)


def progressive_preview(data: PointCloudData, max_points: int = 300_000) -> PointCloudData:
    """Fast first-screen preview without mutating the full cloud."""
    return data.subset(sample_indices(len(data.points), max_points))


def voxel_downsample_data(
    data: PointCloudData, voxel_size: float = 0.5, use_gpu: bool | str = False
) -> PointCloudData:
    """Voxel downsample while preserving per-point attributes by voxel aggregation."""
    if len(data.points) == 0:
        return data
    voxel_size = max(float(voxel_size), 1e-9)
    gpu_preference = _normalize_gpu_preference(use_gpu)
    if gpu_preference != "cpu":
        cp, status = get_cupy(gpu_preference)
        if cp is not None:
            try:
                return _voxel_downsample_data_cupy(data, voxel_size, cp, status.label)
            except Exception as exc:  # pragma: no cover - depends on host CUDA stack.
                logger.warning("GPU voxel downsample failed; falling back to CPU: %s", exc)
    origin = data.points.min(axis=0)
    voxel = np.floor((data.points - origin) / voxel_size).astype(np.int64)
    _, inverse = np.unique(voxel, axis=0, return_inverse=True)
    groups = int(inverse.max()) + 1
    counts = np.bincount(inverse).astype(np.float64)

    points = np.zeros((groups, 3), dtype=np.float64)
    for dim in range(3):
        points[:, dim] = np.bincount(inverse, weights=data.points[:, dim]) / counts

    colors = _aggregate_mean(data.colors, inverse, groups, counts)
    normals = _aggregate_normals(data.normals, inverse, groups, counts)
    intensities = _aggregate_mean_1d(data.intensities, inverse, groups, counts)
    classifications = _aggregate_mode(data.classifications, inverse, groups)
    meta = dict(data.metadata)
    meta.update(
        {
            "voxel_size": voxel_size,
            "source_point_count": len(data.points),
            "compute_backend": "cpu",
        }
    )
    return PointCloudData(
        points,
        colors=colors,
        classifications=classifications,
        intensities=intensities,
        normals=normals,
        metadata=meta,
    )


def _normalize_gpu_preference(use_gpu: bool | str) -> str:
    if isinstance(use_gpu, str):
        value = use_gpu.strip().lower()
        if value in {"1", "true", "yes", "on", "gpu", "cuda"}:
            return "auto"
        if value in {"auto", "cupy", "cpu"}:
            return value
        return "cpu"
    return "auto" if use_gpu else "cpu"


def _voxel_downsample_data_cupy(
    data: PointCloudData, voxel_size: float, cp, backend_label: str
) -> PointCloudData:
    pts = cp.asarray(data.points, dtype=cp.float64)
    origin = cp.min(pts, axis=0)
    voxel = cp.floor((pts - origin) / voxel_size).astype(cp.int64)
    _, inverse = cp.unique(voxel, axis=0, return_inverse=True)
    groups = int(cp.max(inverse).get()) + 1
    counts = cp.bincount(inverse, minlength=groups).astype(cp.float64)

    out_points = cp.zeros((groups, 3), dtype=cp.float64)
    for dim in range(3):
        out_points[:, dim] = cp.bincount(inverse, weights=pts[:, dim], minlength=groups) / counts

    colors = _aggregate_mean_cupy(data.colors, inverse, groups, counts, cp)
    normals = _aggregate_normals_cupy(data.normals, inverse, groups, counts, cp)
    intensities = _aggregate_mean_1d_cupy(data.intensities, inverse, groups, counts, cp)
    inverse_cpu = cp.asnumpy(inverse)
    classifications = _aggregate_mode(data.classifications, inverse_cpu, groups)
    meta = dict(data.metadata)
    meta.update(
        {
            "voxel_size": voxel_size,
            "source_point_count": len(data.points),
            "compute_backend": "cupy",
            "gpu_backend": backend_label,
        }
    )
    return PointCloudData(
        cp.asnumpy(out_points),
        colors=colors,
        classifications=classifications,
        intensities=intensities,
        normals=normals,
        metadata=meta,
    )


def _aggregate_mean_cupy(
    values: Optional[np.ndarray], inverse, groups: int, counts, cp
) -> Optional[np.ndarray]:
    if values is None:
        return None
    src = cp.asarray(values, dtype=cp.float64)
    out = cp.zeros((groups, src.shape[1]), dtype=cp.float64)
    for dim in range(src.shape[1]):
        out[:, dim] = cp.bincount(inverse, weights=src[:, dim], minlength=groups) / counts
    return cp.asnumpy(out)


def _aggregate_mean_1d_cupy(
    values: Optional[np.ndarray], inverse, groups: int, counts, cp
) -> Optional[np.ndarray]:
    if values is None:
        return None
    src = cp.asarray(values, dtype=cp.float64)
    out = cp.bincount(inverse, weights=src, minlength=groups) / counts
    return cp.asnumpy(out).astype(np.float32)


def _aggregate_normals_cupy(
    values: Optional[np.ndarray], inverse, groups: int, counts, cp
) -> Optional[np.ndarray]:
    normals = _aggregate_mean_cupy(values, inverse, groups, counts, cp)
    if normals is None:
        return None
    length = np.linalg.norm(normals, axis=1)
    good = length > 1e-12
    normals[good] /= length[good, None]
    return normals


def _aggregate_mean(
    values: Optional[np.ndarray], inverse: np.ndarray, groups: int, counts: np.ndarray
) -> Optional[np.ndarray]:
    if values is None:
        return None
    out = np.zeros((groups, values.shape[1]), dtype=np.float64)
    for dim in range(values.shape[1]):
        out[:, dim] = np.bincount(inverse, weights=values[:, dim]) / counts
    return out


def _aggregate_mean_1d(
    values: Optional[np.ndarray], inverse: np.ndarray, groups: int, counts: np.ndarray
) -> Optional[np.ndarray]:
    if values is None:
        return None
    return (np.bincount(inverse, weights=values) / counts).astype(np.float32)


def _aggregate_normals(
    values: Optional[np.ndarray], inverse: np.ndarray, groups: int, counts: np.ndarray
) -> Optional[np.ndarray]:
    normals = _aggregate_mean(values, inverse, groups, counts)
    if normals is None:
        return None
    length = np.linalg.norm(normals, axis=1)
    good = length > 1e-12
    normals[good] /= length[good, None]
    return normals


def _aggregate_mode(
    values: Optional[np.ndarray], inverse: np.ndarray, groups: int
) -> Optional[np.ndarray]:
    if values is None:
        return None
    out = np.zeros(groups, dtype=np.int32)
    for group in range(groups):
        vals = values[inverse == group].astype(np.int32)
        if len(vals):
            unique, counts = np.unique(vals, return_counts=True)
            out[group] = int(unique[np.argmax(counts)])
    return out


def farthest_point_sample(points: np.ndarray, num_samples: int) -> np.ndarray:
    """FPS (Farthest Point Sampling) returning indices of selected points."""
    n = len(points)
    if num_samples >= n:
        return np.arange(n, dtype=np.int64)
    idx = np.zeros(num_samples, dtype=np.int64)
    dist = np.full(n, np.inf, dtype=np.float32)
    idx[0] = np.random.randint(0, n)
    farthest = idx[0]
    for i in range(1, num_samples):
        diff = points - points[farthest]
        d2 = np.sum(diff * diff, axis=1)
        mask = d2 < dist
        dist[mask] = d2[mask]
        farthest = int(np.argmax(dist))
        idx[i] = farthest
    return idx


# ═══════════════ Filtering ═══════════════


def statistical_outlier_removal(pcd, nb_neighbors: int = 20, std_ratio: float = 2.0):
    """Remove points whose average distance to neighbors exceeds mean + std_ratio * std."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    cl, ind = pcd.remove_statistical_outlier(nb_neighbors, std_ratio)
    inliers = pcd.select_by_index(ind)
    outliers = pcd.select_by_index(ind, invert=True)
    return inliers, outliers


def statistical_outlier_removal_data(
    data: PointCloudData, nb_neighbors: int = 20, std_ratio: float = 2.0
) -> tuple[PointCloudData, PointCloudData]:
    """Open3D SOR with attribute-preserving inlier/outlier subsets."""
    _get_o3d()
    pcd = data.to_o3d()
    _, indices = pcd.remove_statistical_outlier(int(nb_neighbors), float(std_ratio))
    inlier_idx = np.asarray(indices, dtype=np.int64)
    mask = np.ones(len(data.points), dtype=bool)
    mask[inlier_idx] = False
    return data.subset(inlier_idx), data.subset(np.nonzero(mask)[0])


def radius_outlier_removal(pcd, nb_points: int = 16, radius: float = 0.5):
    """Remove points with fewer than nb_points neighbors within radius."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    cl, ind = pcd.remove_radius_outlier(nb_points, radius)
    return pcd.select_by_index(ind)


def radius_outlier_removal_data(
    data: PointCloudData, nb_points: int = 16, radius: float = 0.5
) -> tuple[PointCloudData, PointCloudData]:
    """Radius outlier removal with attribute-preserving subsets."""
    _get_o3d()
    pcd = data.to_o3d()
    _, indices = pcd.remove_radius_outlier(int(nb_points), float(radius))
    inlier_idx = np.asarray(indices, dtype=np.int64)
    mask = np.ones(len(data.points), dtype=bool)
    mask[inlier_idx] = False
    return data.subset(inlier_idx), data.subset(np.nonzero(mask)[0])


def crop_by_bounding_box(pcd, min_bound: np.ndarray, max_bound: np.ndarray):
    """Crop point cloud to axis-aligned bounding box."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    bbox = o3d.geometry.AxisAlignedBoundingBox(
        min_bound.astype(np.float64), max_bound.astype(np.float64)
    )
    return pcd.crop(bbox)


def crop_by_bounds_data(
    data: PointCloudData, min_bound: np.ndarray, max_bound: np.ndarray
) -> tuple[PointCloudData, PointCloudData]:
    """Crop points inside an axis-aligned 3D bounding box."""
    min_bound = np.asarray(min_bound, dtype=np.float64)[:3]
    max_bound = np.asarray(max_bound, dtype=np.float64)[:3]
    mask = np.all((data.points >= min_bound) & (data.points <= max_bound), axis=1)
    return data.subset(np.nonzero(mask)[0]), data.subset(np.nonzero(~mask)[0])


def crop_by_polygon(pcd, polygon_2d: np.ndarray, axis: str = "z"):
    """Crop by 2D polygon in the XY plane (or XZ/YZ). Returns (inliers, outliers)."""
    if isinstance(pcd, np.ndarray):
        pts = pcd
    else:
        pts = np.asarray(pcd.points)
    from shapely.geometry import Point, Polygon

    poly = Polygon(polygon_2d[:, :2])
    axis_map = {"z": (0, 1), "y": (0, 2), "x": (1, 2)}
    ix, iy = axis_map.get(axis, (0, 1))
    mask = np.array([poly.contains(Point(p[ix], p[iy])) for p in pts])
    inliers = pts[mask]
    outliers = pts[~mask]
    return inliers, outliers


def crop_by_polygon_data(
    data: PointCloudData, polygon_2d: np.ndarray, axis: str = "z"
) -> tuple[PointCloudData, PointCloudData]:
    """Crop by 2D polygon and keep all attributes."""
    axis_map = {"z": (0, 1), "y": (0, 2), "x": (1, 2)}
    ix, iy = axis_map.get(axis, (0, 1))
    mask = _points_in_polygon(data.points[:, [ix, iy]], np.asarray(polygon_2d, dtype=np.float64))
    return data.subset(np.nonzero(mask)[0]), data.subset(np.nonzero(~mask)[0])


def clip_by_plane_data(
    data: PointCloudData, plane_origin: np.ndarray, plane_normal: np.ndarray
) -> tuple[PointCloudData, PointCloudData]:
    """Split a cloud by a plane. Returns (positive_side, negative_side)."""
    origin = np.asarray(plane_origin, dtype=np.float64)[:3]
    normal = np.asarray(plane_normal, dtype=np.float64)[:3]
    norm = np.linalg.norm(normal)
    if norm <= 1e-12:
        raise ValueError("plane_normal must be non-zero")
    signed = (data.points - origin) @ (normal / norm)
    return data.subset(np.nonzero(signed >= 0)[0]), data.subset(np.nonzero(signed < 0)[0])


def _points_in_polygon(points_2d: np.ndarray, polygon_2d: np.ndarray) -> np.ndarray:
    x = points_2d[:, 0]
    y = points_2d[:, 1]
    poly = np.asarray(polygon_2d, dtype=np.float64)
    if len(poly) < 3:
        return np.zeros(len(points_2d), dtype=bool)
    x1, y1 = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    inside = np.zeros(len(points_2d), dtype=bool)
    for xa, ya, xb, yb in zip(x1, y1, x2, y2):
        crosses = ((ya > y) != (yb > y)) & (
            x < (xb - xa) * (y - ya) / ((yb - ya) if abs(yb - ya) > 1e-12 else 1e-12) + xa
        )
        inside ^= crosses
    return inside


def nearest_point(points: np.ndarray, query: np.ndarray) -> tuple[int, float]:
    """Return nearest point index and distance."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) == 0:
        return -1, float("inf")
    diff = pts[:, :3] - np.asarray(query, dtype=np.float64)[:3]
    dist2 = np.einsum("ij,ij->i", diff, diff)
    idx = int(np.argmin(dist2))
    return idx, float(np.sqrt(dist2[idx]))


# ═══════════════ Ground filtering ═══════════════


def cloth_simulation_filter(
    pcd,
    cloth_resolution: float = 1.0,
    max_slope_degrees: float = 15.0,
    height_threshold: float = 0.3,
):
    """CSF ground filtering using Open3D segment_plane fallback + slope filter.

    Falls back to RANSAC plane segmentation if Open3D < 0.18.
    Returns (ground_pcd, non_ground_pcd).
    """
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)

    pts = np.asarray(pcd.points)
    if len(pts) < 3:
        return pcd, o3d.geometry.PointCloud()

    plane_model, inliers = pcd.segment_plane(
        distance_threshold=height_threshold,
        ransac_n=3,
        num_iterations=1000,
    )
    ground = pcd.select_by_index(inliers)
    non_ground = pcd.select_by_index(inliers, invert=True)

    plane_normal = np.array(plane_model[:3])
    slope_rad = np.arccos(np.abs(plane_normal[2]) / np.linalg.norm(plane_normal))
    slope_deg = float(np.degrees(slope_rad))
    if slope_deg > max_slope_degrees:
        logger.info(f"CSF: plane slope {slope_deg:.1f} exceeds limit; using all non-ground")
        return o3d.geometry.PointCloud(), pcd

    logger.info(f"CSF: ground={len(inliers)}, non_ground={len(pts) - len(inliers)}")
    return ground, non_ground


def progressive_morphological_filter_data(
    data: PointCloudData,
    cell_size: float = 1.0,
    height_threshold: float = 0.5,
    max_window_cells: int = 5,
) -> tuple[PointCloudData, PointCloudData]:
    """Simplified progressive morphological ground filter.

    A minimum-z surface is iteratively relaxed with larger windows, then points
    within height_threshold are classified as ground.
    """
    dem_info = pointcloud_to_grids(data, cell_size=cell_size)
    dem = dem_info["dem"]
    if dem.size == 0:
        return data.subset(np.array([], dtype=np.int64)), data
    ground = dem.copy()
    for radius in range(1, max(1, max_window_cells) + 1):
        ground = _minimum_filter(ground, radius)
    rows, cols, origin = _grid_coords(data.points, cell_size)
    local_ground = ground[rows, cols]
    mask = np.isfinite(local_ground) & ((data.points[:, 2] - local_ground) <= height_threshold)
    return data.subset(np.nonzero(mask)[0]), data.subset(np.nonzero(~mask)[0])


def smrf_filter_data(
    data: PointCloudData,
    cell_size: float = 1.0,
    height_threshold: float = 0.5,
    slope_threshold: float = 0.2,
) -> tuple[PointCloudData, PointCloudData]:
    """Small-footprint SMRF-style ground classifier using min surface + slope allowance."""
    dem_info = pointcloud_to_grids(data, cell_size=cell_size)
    dem = dem_info["dem"]
    if dem.size == 0:
        return data.subset(np.array([], dtype=np.int64)), data
    filled = _fill_nan_nearest(dem)
    rows, cols, _ = _grid_coords(data.points, cell_size)
    local_ground = filled[rows, cols]
    dz = data.points[:, 2] - local_ground
    allowance = height_threshold + slope_threshold * cell_size
    mask = dz <= allowance
    return data.subset(np.nonzero(mask)[0]), data.subset(np.nonzero(~mask)[0])


def classify_ground(
    data: PointCloudData, ground: PointCloudData, non_ground: PointCloudData
) -> PointCloudData:
    """Combine ground/non-ground subsets and write LAS-style classification codes."""
    points = np.vstack([ground.points, non_ground.points])
    colors = _combine_optional_2d(
        ground.colors, len(ground.points), non_ground.colors, len(non_ground.points), 3
    )
    normals = _combine_optional_2d(
        ground.normals, len(ground.points), non_ground.normals, len(non_ground.points), 3
    )
    intensities = _combine_optional_1d(
        ground.intensities,
        len(ground.points),
        non_ground.intensities,
        len(non_ground.points),
        np.float32,
    )
    classifications = np.concatenate(
        [np.full(len(ground.points), 2, dtype=np.int32), np.full(len(non_ground.points), 1)]
    )
    meta = dict(data.metadata)
    meta["ground_classified"] = True
    return PointCloudData(
        points,
        colors=colors,
        classifications=classifications,
        intensities=intensities,
        normals=normals,
        metadata=meta,
    )


def _combine_optional_2d(
    first: Optional[np.ndarray],
    first_len: int,
    second: Optional[np.ndarray],
    second_len: int,
    width: int,
) -> Optional[np.ndarray]:
    if first is None and second is None:
        return None
    a = first if first is not None else np.zeros((first_len, width), dtype=np.float64)
    b = second if second is not None else np.zeros((second_len, width), dtype=np.float64)
    return np.vstack([a, b]) if len(a) or len(b) else np.empty((0, width), dtype=np.float64)


def _combine_optional_1d(
    first: Optional[np.ndarray],
    first_len: int,
    second: Optional[np.ndarray],
    second_len: int,
    dtype,
) -> Optional[np.ndarray]:
    if first is None and second is None:
        return None
    a = first if first is not None else np.zeros(first_len, dtype=dtype)
    b = second if second is not None else np.zeros(second_len, dtype=dtype)
    return np.concatenate([a, b]).astype(dtype, copy=False)


def _minimum_filter(values: np.ndarray, radius: int) -> np.ndarray:
    padded = np.pad(values, radius, mode="edge")
    out = np.empty_like(values)
    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            window = padded[row : row + 2 * radius + 1, col : col + 2 * radius + 1]
            finite = window[np.isfinite(window)]
            out[row, col] = float(finite.min()) if finite.size else np.nan
    return out


def _fill_nan_nearest(values: np.ndarray) -> np.ndarray:
    out = values.copy()
    if np.isfinite(out).all():
        return out
    finite = np.isfinite(out)
    fill = float(np.nanmedian(out)) if finite.any() else 0.0
    out[~finite] = fill
    return out


# ═══════════════ Normals ═══════════════


def estimate_normals(pcd, radius: float = 0.0, max_nn: int = 30):
    """Estimate normals via Open3D hybrid search."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    pts = np.asarray(pcd.points)
    if len(pts) == 0:
        return pcd
    if radius <= 0:
        bbox = pcd.get_axis_aligned_bounding_box()
        diag = float(np.linalg.norm(bbox.get_max_bound() - bbox.get_min_bound()))
        radius = max(diag * 0.01, 1e-6)
    params = o3d.geometry.KDTreeSearchParamHybrid(radius=float(radius), max_nn=int(max_nn))
    pcd.estimate_normals(search_param=params)
    pcd.orient_normals_towards_camera_location()
    return pcd


def estimate_normals_data(
    data: PointCloudData, radius: float = 0.0, max_nn: int = 30
) -> PointCloudData:
    pcd = estimate_normals(data.to_o3d(), radius=radius, max_nn=max_nn)
    _, _, normals = from_o3d_pointcloud(pcd)
    return PointCloudData(
        data.points,
        colors=data.colors,
        classifications=data.classifications,
        intensities=data.intensities,
        normals=normals,
        metadata=dict(data.metadata),
    )


def local_roughness_curvature(points: np.ndarray, k: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """Compute simple local roughness and curvature from k nearest neighbours."""
    pts = np.asarray(points, dtype=np.float64)[:, :3]
    n = len(pts)
    if n == 0:
        return np.array([]), np.array([])
    k = min(max(3, int(k)), n)
    roughness = np.zeros(n, dtype=np.float32)
    curvature = np.zeros(n, dtype=np.float32)
    try:
        from scipy.spatial import cKDTree

        _, neighbours = cKDTree(pts).query(pts, k=k)
        if k == 1:
            neighbours = neighbours[:, None]
    except Exception:
        neighbours = None
    for i, pt in enumerate(pts):
        if neighbours is None:
            dist2 = np.einsum("ij,ij->i", pts - pt, pts - pt)
            idx = np.argpartition(dist2, k - 1)[:k]
        else:
            idx = np.asarray(neighbours[i], dtype=np.int64)
        neigh = pts[idx]
        roughness[i] = float(np.std(neigh[:, 2]))
        centered = neigh - neigh.mean(axis=0)
        cov = centered.T @ centered / max(len(neigh) - 1, 1)
        eigvals = np.sort(np.maximum(np.linalg.eigvalsh(cov), 0.0))
        total = float(eigvals.sum())
        curvature[i] = float(eigvals[0] / total) if total > 1e-12 else 0.0
    return roughness, curvature


def normalize_height(
    data: PointCloudData, ground: PointCloudData, cell_size: float = 1.0
) -> PointCloudData:
    """Subtract a gridded ground surface from point z values."""
    grid_info = pointcloud_to_grids(ground, cell_size=cell_size)
    ground_grid = grid_info["dem"]
    if ground_grid.size == 0:
        return data
    ground_grid = _fill_nan_nearest(ground_grid)
    rows, cols, _ = _grid_coords(data.points, cell_size, origin=grid_info["origin"])
    rows = np.clip(rows, 0, ground_grid.shape[0] - 1)
    cols = np.clip(cols, 0, ground_grid.shape[1] - 1)
    points = data.points.copy()
    points[:, 2] = points[:, 2] - ground_grid[rows, cols]
    meta = dict(data.metadata)
    meta["height_normalized"] = True
    return PointCloudData(
        points,
        colors=data.colors,
        classifications=data.classifications,
        intensities=data.intensities,
        normals=data.normals,
        metadata=meta,
    )


def pointcloud_to_grids(
    data: PointCloudData, cell_size: float = 1.0, use_gpu: bool | str = False
) -> dict[str, np.ndarray]:
    """Rasterize point cloud to DEM(min), DSM(max), CHM(max-min), count."""
    pts = np.asarray(data.points, dtype=np.float64)
    if len(pts) == 0:
        empty = np.empty((0, 0), dtype=np.float32)
        return {
            "dem": empty,
            "dsm": empty,
            "chm": empty,
            "count": empty.astype(np.int32),
            "origin": np.zeros(2, dtype=np.float64),
            "cell_size": float(cell_size),
            "compute_backend": "cpu",
        }
    cell_size = max(float(cell_size), 1e-9)
    gpu_preference = _normalize_gpu_preference(use_gpu)
    if gpu_preference != "cpu":
        cp, status = get_cupy(gpu_preference)
        if cp is not None:
            try:
                return _pointcloud_to_grids_cupy(data, cell_size, cp, status.label)
            except Exception as exc:  # pragma: no cover - depends on host CUDA stack.
                logger.warning("GPU point cloud grid failed; falling back to CPU: %s", exc)
    mins = pts[:, :2].min(axis=0)
    cols = np.floor((pts[:, 0] - mins[0]) / cell_size).astype(np.int64)
    rows = np.floor((pts[:, 1] - mins[1]) / cell_size).astype(np.int64)
    shape = (int(rows.max()) + 1, int(cols.max()) + 1)
    dem = np.full(shape, np.inf, dtype=np.float32)
    dsm = np.full(shape, -np.inf, dtype=np.float32)
    count = np.zeros(shape, dtype=np.int32)
    np.minimum.at(dem, (rows, cols), pts[:, 2].astype(np.float32))
    np.maximum.at(dsm, (rows, cols), pts[:, 2].astype(np.float32))
    np.add.at(count, (rows, cols), 1)
    dem[~np.isfinite(dem)] = np.nan
    dsm[~np.isfinite(dsm)] = np.nan
    chm = dsm - dem
    return {
        "dem": dem,
        "dsm": dsm,
        "chm": chm.astype(np.float32),
        "count": count,
        "origin": mins,
        "cell_size": cell_size,
        "compute_backend": "cpu",
    }


def _pointcloud_to_grids_cupy(
    data: PointCloudData, cell_size: float, cp, backend_label: str
) -> dict[str, np.ndarray]:
    pts = cp.asarray(data.points, dtype=cp.float64)
    mins = cp.min(pts[:, :2], axis=0)
    cols = cp.floor((pts[:, 0] - mins[0]) / cell_size).astype(cp.int64)
    rows = cp.floor((pts[:, 1] - mins[1]) / cell_size).astype(cp.int64)
    shape = (int(cp.max(rows).get()) + 1, int(cp.max(cols).get()) + 1)
    dem = cp.full(shape, cp.inf, dtype=cp.float32)
    dsm = cp.full(shape, -cp.inf, dtype=cp.float32)
    count = cp.zeros(shape, dtype=cp.int32)
    z = pts[:, 2].astype(cp.float32)
    cp.minimum.at(dem, (rows, cols), z)
    cp.maximum.at(dsm, (rows, cols), z)
    cp.add.at(count, (rows, cols), 1)
    dem = cp.where(cp.isfinite(dem), dem, cp.nan)
    dsm = cp.where(cp.isfinite(dsm), dsm, cp.nan)
    chm = dsm - dem
    return {
        "dem": cp.asnumpy(dem),
        "dsm": cp.asnumpy(dsm),
        "chm": cp.asnumpy(chm).astype(np.float32),
        "count": cp.asnumpy(count),
        "origin": cp.asnumpy(mins),
        "cell_size": cell_size,
        "compute_backend": "cupy",
        "gpu_backend": backend_label,
    }


def _grid_coords(
    points: np.ndarray, cell_size: float, origin: Optional[np.ndarray] = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pts = np.asarray(points, dtype=np.float64)
    origin = np.asarray(origin, dtype=np.float64) if origin is not None else pts[:, :2].min(axis=0)
    cols = np.floor((pts[:, 0] - origin[0]) / max(cell_size, 1e-9)).astype(np.int64)
    rows = np.floor((pts[:, 1] - origin[1]) / max(cell_size, 1e-9)).astype(np.int64)
    return rows, cols, origin


# ═══════════════ Registration ═══════════════


def icp_register(
    source, target, max_correspondence_distance: float = 1.0, max_iterations: int = 50
) -> Tuple[np.ndarray, float]:
    """Point-to-point ICP registration. Returns (4x4 transform, fitness)."""
    _get_o3d()
    if isinstance(source, np.ndarray):
        source = to_o3d_pointcloud(source)
    if isinstance(target, np.ndarray):
        target = to_o3d_pointcloud(target)

    threshold = max_correspondence_distance
    reg = o3d.pipelines.registration.registration_icp(
        source,
        target,
        threshold,
        np.eye(4),
        o3d.pipelines.registration.TransformationEstimationPointToPoint(),
        o3d.pipelines.registration.ICPConvergenceCriteria(
            max_iteration=max_iterations, relative_fitness=1e-6, relative_rmse=1e-6
        ),
    )
    logger.info(f"ICP: fitness={reg.fitness:.4f}, rmse={reg.inlier_rmse:.4f}")
    return reg.transformation, float(reg.fitness)


def transform_pointcloud(pcd, transform: np.ndarray):
    """Apply 4x4 rigid transform to point cloud."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    return pcd.transform(transform)


# ═══════════════ Volume / metrics ═══════════════


def compute_convex_hull_volume(pcd) -> float:
    """Volume of convex hull."""
    _get_o3d()
    if isinstance(pcd, np.ndarray):
        pcd = to_o3d_pointcloud(pcd)
    hull, _ = pcd.compute_convex_hull()
    return float(hull.get_volume())


def cut_fill_volume(ground_pcd, design_pcd, cell_size: float = 1.0) -> dict[str, float]:
    """Raster-based cut/fill between ground and design surfaces.

    Returns dict with cut_volume, fill_volume, net_volume (positive = cut).
    """
    g_pts = np.asarray(ground_pcd.points) if not isinstance(ground_pcd, np.ndarray) else ground_pcd
    d_pts = np.asarray(design_pcd.points) if not isinstance(design_pcd, np.ndarray) else design_pcd

    g_x, g_y, g_z = g_pts[:, 0], g_pts[:, 1], g_pts[:, 2]
    d_x, d_y, d_z = d_pts[:, 0], d_pts[:, 1], d_pts[:, 2]

    x_min = min(g_x.min(), d_x.min())
    x_max = max(g_x.max(), d_x.max())
    y_min = min(g_y.min(), d_y.min())
    y_max = max(g_y.max(), d_y.max())

    cols = int(np.ceil((x_max - x_min) / cell_size))
    rows = int(np.ceil((y_max - y_min) / cell_size))
    cols = max(cols, 2)
    rows = max(rows, 2)

    grid_x = np.linspace(x_min, x_max, cols)
    grid_y = np.linspace(y_min, y_max, rows)

    from scipy.interpolate import griddata

    g_grid = griddata(
        (g_x, g_y), g_z, (grid_x[None, :], grid_y[:, None]), method="linear", fill_value=np.nan
    )
    d_grid = griddata(
        (d_x, d_y), d_z, (grid_x[None, :], grid_y[:, None]), method="linear", fill_value=np.nan
    )

    diff = d_grid - g_grid
    cell_area = cell_size * cell_size
    cut = float(np.nansum(np.maximum(diff, 0)) * cell_area)
    fill = float(np.nansum(np.maximum(-diff, 0)) * cell_area)
    return {"cut_volume": cut, "fill_volume": fill, "net_volume": cut - fill}


# ═══════════════ Classification helpers ═══════════════


def build_classification_colors(
    class_ids: np.ndarray, custom_map: Optional[dict[int, tuple[float, float, float]]] = None
) -> np.ndarray:
    """Map integer classification IDs to (N,3) RGB colors using LAS standard palette."""
    from core.scene_graph import get_classification_color

    colors = np.zeros((len(class_ids), 3), dtype=np.float32)
    unique = np.unique(class_ids)
    for cid in unique:
        mask = class_ids == cid
        if custom_map and int(cid) in custom_map:
            colors[mask] = custom_map[int(cid)]
        else:
            colors[mask] = get_classification_color(int(cid))
    return colors
