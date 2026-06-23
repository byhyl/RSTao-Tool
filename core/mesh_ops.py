"""Mesh operations: simplification, smoothing, cross-section, volume, texture.

Uses trimesh for format-agnostic loading and Open3D for rendering/computation.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from common.logger import logger

o3d = None
trimesh = None
_O3D_AVAILABLE: bool | None = None
_TRIMESH_AVAILABLE: bool | None = None


def _get_o3d():
    """Import Open3D lazily so app startup is not tied to native 3D libs."""
    global o3d, _O3D_AVAILABLE
    if o3d is not None:
        return o3d
    if _O3D_AVAILABLE is False:
        raise RuntimeError("open3d required")
    try:
        import open3d as _o3d
    except ImportError as exc:
        _O3D_AVAILABLE = False
        raise RuntimeError("open3d required") from exc
    o3d = _o3d
    _O3D_AVAILABLE = True
    return o3d


def _get_trimesh():
    """Import trimesh lazily; mesh support is optional until a mesh is opened."""
    global trimesh, _TRIMESH_AVAILABLE
    if trimesh is not None:
        return trimesh
    if _TRIMESH_AVAILABLE is False:
        raise RuntimeError("trimesh required")
    try:
        import trimesh as _trimesh
    except ImportError as exc:
        _TRIMESH_AVAILABLE = False
        raise RuntimeError("trimesh required") from exc
    trimesh = _trimesh
    _TRIMESH_AVAILABLE = True
    return trimesh


def load_mesh(path: str):
    """Load any mesh format via trimesh, return open3d TriangleMesh."""
    _get_o3d()
    _get_trimesh()
    tm = trimesh.load(path, force="mesh")
    vertices = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(vertices)
    mesh.triangles = o3d.utility.Vector3iVector(faces)
    if hasattr(tm.visual, "vertex_colors") and tm.visual.vertex_colors is not None:
        colors = tm.visual.vertex_colors[:, :3].astype(np.float64) / 255.0
        mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
    mesh.compute_vertex_normals()
    logger.info(f"Loaded mesh: {len(vertices)} vertices, {len(faces)} faces")
    return mesh


def simplify_mesh(mesh, target_number_of_triangles: int = 10000):
    """QEM (Quadric Error Metrics) mesh simplification via Open3D."""
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)
    simplified = mesh.simplify_quadric_decimation(target_number_of_triangles)
    simplified.compute_vertex_normals()
    return simplified


def smooth_mesh(mesh, iterations: int = 10, lambda_filter: float = 0.5):
    """Laplacian smoothing via Open3D filter_smooth_laplacian."""
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)
    smoothed = mesh.filter_smooth_laplacian(iterations, lambda_filter)
    smoothed.compute_vertex_normals()
    return smoothed


def repair_mesh_normals(mesh):
    """Recompute triangle/vertex normals and orient triangles when possible."""
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_non_manifold_edges()
    mesh.compute_triangle_normals()
    mesh.compute_vertex_normals()
    try:
        mesh.orient_triangles()
    except Exception:
        pass
    return mesh


def boundary_edges_from_faces(faces: np.ndarray) -> np.ndarray:
    """Return mesh boundary edges from triangle face indices."""
    faces = np.asarray(faces, dtype=np.int64)
    if faces.size == 0:
        return np.empty((0, 2), dtype=np.int64)
    edges = np.vstack(
        [
            faces[:, [0, 1]],
            faces[:, [1, 2]],
            faces[:, [2, 0]],
        ]
    )
    edges = np.sort(edges, axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return unique[counts == 1]


def mesh_quality_report(mesh) -> dict[str, float | int | bool]:
    """Basic mesh quality metrics for UI diagnostics and tests."""
    vertices = np.asarray(mesh.vertices) if hasattr(mesh, "vertices") else np.asarray(mesh[0])
    faces = np.asarray(mesh.triangles) if hasattr(mesh, "triangles") else np.asarray(mesh[1])
    boundary_edges = boundary_edges_from_faces(faces)
    report = {
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "boundary_edge_count": int(len(boundary_edges)),
        "watertight": bool(len(boundary_edges) == 0 and len(faces) > 0),
    }
    if len(vertices):
        mins = vertices[:, :3].min(axis=0)
        maxs = vertices[:, :3].max(axis=0)
        report["bbox_diag"] = float(np.linalg.norm(maxs - mins))
    else:
        report["bbox_diag"] = 0.0
    return report


def compute_mesh_volume(mesh) -> float:
    """Watertight mesh volume via trimesh."""
    _get_trimesh()
    vertices = np.asarray(mesh.vertices) if not isinstance(mesh, np.ndarray) else mesh
    faces = np.asarray(mesh.triangles) if hasattr(mesh, "triangles") else None
    if faces is None:
        raise ValueError("Mesh has no faces")
    tm = trimesh.Trimesh(vertices=vertices, faces=faces)
    return float(tm.volume) if tm.is_watertight else float(tm.convex_hull.volume)


def mesh_to_pointcloud(mesh, num_points: int = 500000):
    """Sample points from mesh surface. Returns open3d PointCloud."""
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)
    pcd = mesh.sample_points_uniformly(number_of_points=num_points)
    return pcd


def poisson_reconstruct(pointcloud, depth: int = 8, density_quantile: float = 0.02):
    """Poisson surface reconstruction from an Open3D point cloud."""
    _get_o3d()
    pcd = pointcloud if not isinstance(pointcloud, str) else o3d.io.read_point_cloud(pointcloud)
    if not pcd.has_normals():
        pcd.estimate_normals()
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=int(depth)
    )
    if density_quantile > 0 and len(densities):
        densities = np.asarray(densities)
        threshold = np.quantile(densities, float(density_quantile))
        mesh.remove_vertices_by_mask(densities < threshold)
    mesh.compute_vertex_normals()
    return mesh


def ball_pivoting_reconstruct(pointcloud, radii: Optional[list[float]] = None):
    """Ball Pivoting reconstruction from an Open3D point cloud."""
    _get_o3d()
    pcd = pointcloud if not isinstance(pointcloud, str) else o3d.io.read_point_cloud(pointcloud)
    if not pcd.has_normals():
        pcd.estimate_normals()
    if radii is None:
        pts = np.asarray(pcd.points)
        diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) if len(pts) else 1.0
        base = max(diag * 0.01, 1e-6)
        radii = [base, base * 2]
    mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
        pcd, o3d.utility.DoubleVector([float(v) for v in radii])
    )
    mesh.compute_vertex_normals()
    return mesh


def cross_section(mesh, plane_origin: np.ndarray, plane_normal: np.ndarray):
    """Extract cross-section polyline from mesh at a given plane.

    plane_origin: (3,) point on plane
    plane_normal: (3,) plane normal direction
    Returns (N,3) numpy array of intersection polyline vertices.
    """
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)

    a, b, c = plane_normal.astype(np.float64)
    d_val = -float(np.dot(plane_normal, plane_origin))
    plane = np.array([a, b, c, d_val], dtype=np.float64)

    verts = np.asarray(mesh.vertices)
    tris = np.asarray(mesh.triangles)

    segments = []
    for tri in tris:
        v0, v1, v2 = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        d0 = a * v0[0] + b * v0[1] + c * v0[2] + d_val
        d1 = a * v1[0] + b * v1[1] + c * v1[2] + d_val
        d2 = a * v2[0] + b * v2[1] + c * v2[2] + d_val
        side0, side1, side2 = d0 >= 0, d1 >= 0, d2 >= 0

        if side0 == side1 == side2:
            continue

        edge_pairs = []
        if side0 != side1:
            t = d0 / (d0 - d1) if abs(d0 - d1) > 1e-12 else 0.5
            edge_pairs.append(v0 + t * (v1 - v0))
        if side1 != side2:
            t = d1 / (d1 - d2) if abs(d1 - d2) > 1e-12 else 0.5
            edge_pairs.append(v1 + t * (v2 - v1))
        if side2 != side0:
            t = d2 / (d2 - d0) if abs(d2 - d0) > 1e-12 else 0.5
            edge_pairs.append(v2 + t * (v0 - v2))
        if len(edge_pairs) == 2:
            segments.append(edge_pairs[0])
            segments.append(edge_pairs[1])
        elif len(edge_pairs) == 3:
            segments.extend(edge_pairs[:2])

    return np.array(segments, dtype=np.float32) if segments else np.empty((0, 3), dtype=np.float32)


def subdivide_mesh(mesh, iterations: int = 1):
    """Loop subdivision via Open3D."""
    _get_o3d()
    if isinstance(mesh, str):
        mesh = o3d.io.read_triangle_mesh(mesh)
    subdivided = mesh
    for _ in range(iterations):
        subdivided = subdivided.subdivide_loop()
    subdivided.compute_vertex_normals()
    return subdivided
