"""Unified project resource inspection for raster, vector, point clouds, and meshes."""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from core.spatial_reference import (
    compute_file_hash,
    read_raster_spatial_ref,
    read_vector_spatial_ref,
)

RASTER_EXTS = {".tif", ".tiff", ".img", ".jp2", ".vrt", ".png", ".jpg", ".jpeg", ".bmp"}
VECTOR_EXTS = {".shp", ".geojson", ".json", ".gpkg", ".dxf"}
POINT_CLOUD_EXTS = {".xyz", ".txt", ".csv", ".pts", ".pcd", ".las", ".laz", ".ply"}
MESH_EXTS = {".obj", ".osgb", ".ply"}
MODEL_EXTS = {".onnx", ".pt", ".pth", ".engine"}


@dataclass
class ResourceRecord:
    resource_id: str
    name: str
    source_path: str
    source_type: str
    extension: str
    size_bytes: int = 0
    file_hash: str = ""
    visible: bool = True
    opacity: float = 1.0
    locked: bool = False
    order: int = 0
    crs: str = ""
    epsg: Optional[int] = None
    bounds: Any = None
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
        return asdict(self)


@dataclass
class ScenePreview:
    vertices: np.ndarray
    faces: Optional[np.ndarray] = None
    colors: Optional[np.ndarray] = None
    warning: str = ""


def classify_resource(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in RASTER_EXTS:
        return "raster"
    if suffix in VECTOR_EXTS:
        return "vector"
    if suffix in POINT_CLOUD_EXTS:
        return "pointcloud"
    if suffix in MESH_EXTS:
        return "mesh"
    if suffix in MODEL_EXTS:
        return "model"
    return "file"


def supported_resource_extensions() -> tuple[str, ...]:
    return tuple(sorted(RASTER_EXTS | VECTOR_EXTS | POINT_CLOUD_EXTS | MESH_EXTS | MODEL_EXTS))


def create_resource_record(path: str | Path, source_type: str | None = None) -> dict:
    resource_path = Path(path)
    suffix = resource_path.suffix.lower()
    inferred = source_type or classify_resource(resource_path)
    stat = resource_path.stat()
    record = ResourceRecord(
        resource_id=compute_resource_id(resource_path),
        name=resource_path.name,
        source_path=str(resource_path),
        source_type=inferred,
        extension=suffix,
        size_bytes=int(stat.st_size),
        file_hash=compute_file_hash(resource_path),
        format_detail=suffix.lstrip(".").upper(),
    )

    if inferred == "raster":
        _fill_raster(record)
    elif inferred == "vector":
        _fill_vector(record)
    elif inferred == "pointcloud":
        _fill_pointcloud(record)
    elif inferred == "mesh":
        _fill_mesh(record)
    elif inferred == "model":
        record.metadata["kind"] = "ML model"

    return record.to_dict()


def compute_resource_id(path: str | Path) -> str:
    p = Path(path)
    try:
        stat = p.stat()
        seed = f"{p.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except Exception:
        seed = str(p)
    import hashlib

    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


def read_scene_preview(path: str | Path, max_points: int = 50000) -> ScenePreview:
    resource_path = Path(path)
    suffix = resource_path.suffix.lower()
    if suffix == ".obj":
        preview = _read_obj_preview(resource_path, max_points=max_points)
        if preview.vertices.size:
            return preview
        trimesh_preview = _read_trimesh_preview(resource_path, max_points=max_points)
        if trimesh_preview is not None:
            return trimesh_preview
        return preview
    if suffix == ".ply":
        preview = _read_ply_preview(resource_path, max_points=max_points)
        if preview.vertices.size or preview.warning:
            return preview
        trimesh_preview = _read_trimesh_preview(resource_path, max_points=max_points)
        if trimesh_preview is not None:
            return trimesh_preview
        return preview
    if suffix == ".pcd":
        pcd_preview = _read_pcd_preview(resource_path, max_points=max_points)
        if pcd_preview is not None:
            return pcd_preview
        return ScenePreview(
            np.empty((0, 3), dtype=np.float32),
            warning="PCD 预览失败；若为二进制压缩 PCD，建议安装 Open3D 后重试。",
        )
    if suffix in {".xyz", ".txt", ".csv", ".pts"}:
        return _read_text_point_preview(resource_path, max_points=max_points)
    if suffix in {".las", ".laz"}:
        las_preview = _read_las_preview(resource_path, max_points=max_points)
        if las_preview is not None:
            return las_preview
        return ScenePreview(
            np.empty((0, 3), dtype=np.float32),
            warning="当前环境未安装 laspy，LAS/LAZ 仅作为资源登记，暂不能内置预览。",
        )
    if suffix == ".osgb":
        return ScenePreview(
            np.empty((0, 3), dtype=np.float32),
            warning="OSGB 为倾斜摄影/场景模型格式，当前内置版先登记资源；真实三维预览建议接入 OSG/Open3D 插件。",
        )
    return ScenePreview(np.empty((0, 3), dtype=np.float32), warning="该资源暂无三维预览。")


def _fill_raster(record: ResourceRecord) -> None:
    ref = read_raster_spatial_ref(record.source_path)
    record.crs = ref.crs
    record.epsg = ref.epsg
    record.bounds = ref.bounds
    record.width = ref.width
    record.height = ref.height
    record.bands = ref.bands
    record.dtype = ref.dtype
    record.warning = ref.warning


def _fill_vector(record: ResourceRecord) -> None:
    ref = read_vector_spatial_ref(record.source_path)
    record.crs = ref.crs
    record.epsg = ref.epsg
    record.bounds = ref.bounds
    record.width = ref.width
    record.dtype = ref.dtype
    record.warning = ref.warning


def _fill_pointcloud(record: ResourceRecord) -> None:
    suffix = record.extension
    if suffix in {".las", ".laz"}:
        if not _fill_las(record):
            record.warning = "LAS/LAZ 需要安装 laspy 后读取点数和范围。"
        return
    if suffix == ".pcd":
        if not _fill_pcd(record):
            record.warning = "PCD 元数据读取失败；若为二进制压缩 PCD，建议安装 Open3D。"
        return
    if suffix == ".ply":
        header = _read_ply_header(Path(record.source_path))
        record.point_count = int(header.get("vertex_count", 0))
        record.face_count = int(header.get("face_count", 0))
        record.vertex_count = record.point_count
        record.source_type = "mesh" if record.face_count else "pointcloud"
        record.format_detail = "PLY"
        return
    stats = _scan_text_points(Path(record.source_path), max_rows=300000)
    record.point_count = stats["count"]
    record.dimensions = stats["dimensions"]
    record.bounds = stats["bounds"]
    record.warning = stats["warning"]


def _fill_mesh(record: ResourceRecord) -> None:
    suffix = record.extension
    if suffix == ".obj":
        stats = _scan_obj(Path(record.source_path), max_vertices=300000)
        record.vertex_count = stats["vertex_count"]
        record.point_count = stats["vertex_count"]
        record.face_count = stats["face_count"]
        record.bounds = stats["bounds"]
        record.warning = stats["warning"]
        record.format_detail = "OBJ"
        if record.vertex_count or record.face_count:
            return
    elif suffix == ".ply":
        header = _read_ply_header(Path(record.source_path))
        record.vertex_count = int(header.get("vertex_count", 0))
        record.point_count = record.vertex_count
        record.face_count = int(header.get("face_count", 0))
        record.format_detail = "PLY"
        if record.vertex_count and not record.face_count:
            record.source_type = "pointcloud"
        if record.vertex_count or record.face_count:
            return
    elif suffix == ".osgb":
        record.format_detail = "OSGB"
        record.warning = "OSGB 已登记为三维模型资源；内置解析需可选 OSG/OpenSceneGraph 后端。"
        return
    if _fill_trimesh(record):
        return


def _fill_las(record: ResourceRecord) -> bool:
    try:
        import laspy

        with laspy.open(record.source_path) as las:
            header = las.header
            record.point_count = int(header.point_count)
            mins = tuple(float(v) for v in header.mins)
            maxs = tuple(float(v) for v in header.maxs)
            record.bounds = tuple(v for pair in zip(mins, maxs) for v in pair)
            record.format_detail = f"LAS {header.version}"
            return True
    except Exception:
        return False


def _fill_trimesh(record: ResourceRecord) -> bool:
    if record.extension == ".osgb":
        return False
    try:
        import trimesh

        mesh = trimesh.load(record.source_path, force="mesh", skip_materials=True)
        vertices = np.asarray(getattr(mesh, "vertices", []))
        faces = np.asarray(getattr(mesh, "faces", []))
        if vertices.size:
            record.vertex_count = int(len(vertices))
            record.point_count = int(len(vertices))
            mins = vertices[:, :3].min(axis=0)
            maxs = vertices[:, :3].max(axis=0)
            record.bounds = tuple(float(v) for pair in zip(mins, maxs) for v in pair)
        if faces.size:
            record.face_count = int(len(faces))
            record.source_type = "mesh"
        record.format_detail = record.extension.lstrip(".").upper()
        return bool(vertices.size or faces.size)
    except Exception:
        return False


def _fill_pcd(record: ResourceRecord) -> bool:
    open3d_stats = _fill_open3d_pointcloud(record)
    if open3d_stats:
        return True
    try:
        header = _read_pcd_header(Path(record.source_path))
        record.point_count = int(header.get("points") or header.get("width") or 0)
        record.dimensions = len(str(header.get("fields", "")).split())
        record.format_detail = f"PCD {header.get('data', '').upper()}".strip()
        if str(header.get("data", "")).lower() == "ascii":
            stats = _scan_pcd_ascii(Path(record.source_path), header)
            record.bounds = stats["bounds"]
            record.warning = stats["warning"]
        elif not record.point_count:
            record.warning = "PCD header 未包含点数。"
        return True
    except Exception:
        return False


def _fill_open3d_pointcloud(record: ResourceRecord) -> bool:
    try:
        import open3d as o3d

        cloud = o3d.io.read_point_cloud(record.source_path)
        points = np.asarray(cloud.points)
        if points.size == 0:
            return False
        record.point_count = int(len(points))
        record.dimensions = 3
        mins = points[:, :3].min(axis=0)
        maxs = points[:, :3].max(axis=0)
        record.bounds = tuple(float(v) for pair in zip(mins, maxs) for v in pair)
        record.format_detail = record.extension.lstrip(".").upper()
        return True
    except Exception:
        return False


def _scan_text_points(path: Path, max_rows: int = 300000) -> dict:
    count = 0
    dims = 0
    mins = None
    maxs = None
    warning = ""
    for values in _iter_numeric_rows(path):
        if len(values) < 3:
            continue
        point = np.asarray(values[:3], dtype=np.float64)
        if mins is None:
            mins = point.copy()
            maxs = point.copy()
            dims = len(values)
        else:
            mins = np.minimum(mins, point)
            maxs = np.maximum(maxs, point)
        count += 1
        if count >= max_rows:
            warning = f"仅扫描前 {max_rows} 个点用于元数据估计。"
            break
    bounds = tuple(float(v) for pair in zip(mins, maxs) for v in pair) if mins is not None else None
    return {"count": count, "dimensions": dims, "bounds": bounds, "warning": warning}


def _scan_obj(path: Path, max_vertices: int = 300000) -> dict:
    vertex_count = 0
    face_count = 0
    mins = None
    maxs = None
    warning = ""
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.strip().split()
                if len(parts) >= 4:
                    point = np.asarray([float(parts[1]), float(parts[2]), float(parts[3])])
                    if mins is None:
                        mins = point.copy()
                        maxs = point.copy()
                    else:
                        mins = np.minimum(mins, point)
                        maxs = np.maximum(maxs, point)
                vertex_count += 1
                if vertex_count >= max_vertices and not warning:
                    warning = f"仅扫描前 {max_vertices} 个顶点用于范围估计。"
            elif line.startswith("f "):
                face_count += 1
    bounds = tuple(float(v) for pair in zip(mins, maxs) for v in pair) if mins is not None else None
    return {
        "vertex_count": vertex_count,
        "face_count": face_count,
        "bounds": bounds,
        "warning": warning,
    }


def _read_obj_preview(path: Path, max_points: int = 50000) -> ScenePreview:
    vertices = []
    faces = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.strip().split()
                if len(parts) >= 4:
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                idx = []
                for token in line.strip().split()[1:]:
                    raw = token.split("/")[0]
                    if raw:
                        idx.append(int(raw) - 1)
                if len(idx) >= 3:
                    for i in range(1, len(idx) - 1):
                        faces.append([idx[0], idx[i], idx[i + 1]])
            if len(vertices) >= max_points:
                break
    return ScenePreview(_sample_vertices(vertices, max_points), np.asarray(faces, dtype=np.int32))


def _read_las_preview(path: Path, max_points: int = 50000) -> ScenePreview | None:
    try:
        import laspy

        las = laspy.read(path)
        total = len(las.x)
        if total == 0:
            return ScenePreview(np.empty((0, 3), dtype=np.float32))
        if total > max_points:
            idx = np.linspace(0, total - 1, max_points).astype(np.int64)
            points = np.column_stack([las.x[idx], las.y[idx], las.z[idx]])
        else:
            points = np.column_stack([las.x, las.y, las.z])
        colors = None
        if all(hasattr(las, name) for name in ("red", "green", "blue")):
            if total > max_points:
                colors = np.column_stack([las.red[idx], las.green[idx], las.blue[idx]])
            else:
                colors = np.column_stack([las.red, las.green, las.blue])
            colors = np.clip(colors.astype(np.float32) / 65535.0, 0, 1)
        return ScenePreview(points.astype(np.float32), colors=colors)
    except Exception:
        return None


def _read_open3d_point_preview(path: Path, max_points: int = 50000) -> ScenePreview | None:
    try:
        import open3d as o3d

        cloud = o3d.io.read_point_cloud(str(path))
        points = np.asarray(cloud.points, dtype=np.float32)
        if points.size == 0:
            return None
        colors = np.asarray(cloud.colors, dtype=np.float32) if cloud.has_colors() else None
        if len(points) > max_points:
            idx = np.linspace(0, len(points) - 1, max_points).astype(np.int64)
            points = points[idx]
            if colors is not None and len(colors):
                colors = colors[idx]
        return ScenePreview(points, colors=colors)
    except Exception:
        return None


def _read_pcd_preview(path: Path, max_points: int = 50000) -> ScenePreview | None:
    open3d_preview = _read_open3d_point_preview(path, max_points=max_points)
    if open3d_preview is not None:
        return open3d_preview
    try:
        header = _read_pcd_header(path)
        if str(header.get("data", "")).lower() != "ascii":
            return None
        fields = str(header.get("fields", "")).split()
        x_idx = fields.index("x") if "x" in fields else 0
        y_idx = fields.index("y") if "y" in fields else 1
        z_idx = fields.index("z") if "z" in fields else 2
        rgb_idx = fields.index("rgb") if "rgb" in fields else -1
        points = []
        colors = []
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for _ in range(int(header.get("header_lines", 0))):
                next(fh, "")
            for line in fh:
                parts = line.strip().split()
                if len(parts) <= max(x_idx, y_idx, z_idx):
                    continue
                points.append([float(parts[x_idx]), float(parts[y_idx]), float(parts[z_idx])])
                if rgb_idx >= 0 and len(parts) > rgb_idx:
                    colors.append(_decode_pcd_rgb(float(parts[rgb_idx])))
                if len(points) >= max_points:
                    break
        color_arr = np.asarray(colors, dtype=np.float32) if colors else None
        return ScenePreview(_sample_vertices(points, max_points), colors=color_arr)
    except Exception:
        return None


def _read_trimesh_preview(path: Path, max_points: int = 50000) -> ScenePreview | None:
    if path.suffix.lower() == ".osgb":
        return None
    try:
        import trimesh

        mesh = trimesh.load(path, force="mesh", skip_materials=True)
        vertices = np.asarray(getattr(mesh, "vertices", []), dtype=np.float32)
        faces = np.asarray(getattr(mesh, "faces", []), dtype=np.int32)
        if vertices.size == 0:
            return None
        if len(vertices) > max_points:
            idx = np.linspace(0, len(vertices) - 1, max_points).astype(np.int64)
            remap = {old: new for new, old in enumerate(idx)}
            sampled_vertices = vertices[idx]
            sampled_faces = []
            for face in faces:
                if all(int(v) in remap for v in face):
                    sampled_faces.append([remap[int(v)] for v in face])
            vertices = sampled_vertices
            faces = np.asarray(sampled_faces, dtype=np.int32)
        return ScenePreview(vertices, faces if faces.size else None)
    except Exception:
        return None


def _read_text_point_preview(path: Path, max_points: int = 50000) -> ScenePreview:
    points = []
    for values in _iter_numeric_rows(path):
        if len(values) >= 3:
            points.append(values[:3])
        if len(points) >= max_points:
            break
    return ScenePreview(_sample_vertices(points, max_points))


def _read_ply_preview(path: Path, max_points: int = 50000) -> ScenePreview:
    header = _read_ply_header(path)
    if header.get("format") != "ascii":
        return ScenePreview(
            np.empty((0, 3), dtype=np.float32),
            warning="当前内置预览仅支持 ASCII PLY；二进制 PLY 已登记为资源。",
        )
    vertex_count = int(header.get("vertex_count", 0))
    face_count = int(header.get("face_count", 0))
    header_lines = int(header.get("header_lines", 0))
    vertices = []
    faces = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for _ in range(header_lines):
            next(fh, "")
        for _ in range(vertex_count):
            parts = next(fh, "").strip().split()
            if len(parts) >= 3:
                vertices.append([float(parts[0]), float(parts[1]), float(parts[2])])
        for _ in range(face_count):
            parts = next(fh, "").strip().split()
            if len(parts) >= 4:
                n = int(parts[0])
                idx = [int(v) for v in parts[1 : 1 + n]]
                for i in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[i], idx[i + 1]])
    return ScenePreview(_sample_vertices(vertices, max_points), np.asarray(faces, dtype=np.int32))


def _read_ply_header(path: Path) -> dict:
    info = {"format": "", "vertex_count": 0, "face_count": 0, "header_lines": 0}
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh, start=1):
            stripped = line.strip()
            if stripped.startswith("format "):
                info["format"] = (
                    stripped.split()[1].replace("_little_endian", "").replace("_big_endian", "")
                )
            elif stripped.startswith("element vertex"):
                info["vertex_count"] = int(stripped.split()[-1])
            elif stripped.startswith("element face"):
                info["face_count"] = int(stripped.split()[-1])
            elif stripped == "end_header":
                info["header_lines"] = i
                break
    return info


def _read_pcd_header(path: Path) -> dict:
    info = {"header_lines": 0}
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split(maxsplit=1)
            key = parts[0].lower()
            value = parts[1] if len(parts) > 1 else ""
            if key == "fields":
                info["fields"] = value
            elif key in {"width", "height", "points"}:
                try:
                    info[key] = int(value)
                except Exception:
                    info[key] = 0
            elif key in {"size", "type", "count", "version", "data"}:
                info[key] = value
            if key == "data":
                info["header_lines"] = i
                break
    return info


def _scan_pcd_ascii(path: Path, header: dict) -> dict:
    fields = str(header.get("fields", "")).split()
    x_idx = fields.index("x") if "x" in fields else 0
    y_idx = fields.index("y") if "y" in fields else 1
    z_idx = fields.index("z") if "z" in fields else 2
    count = 0
    mins = None
    maxs = None
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for _ in range(int(header.get("header_lines", 0))):
            next(fh, "")
        for line in fh:
            parts = line.strip().split()
            if len(parts) <= max(x_idx, y_idx, z_idx):
                continue
            point = np.asarray(
                [float(parts[x_idx]), float(parts[y_idx]), float(parts[z_idx])],
                dtype=np.float64,
            )
            if mins is None:
                mins = point.copy()
                maxs = point.copy()
            else:
                mins = np.minimum(mins, point)
                maxs = np.maximum(maxs, point)
            count += 1
    bounds = tuple(float(v) for pair in zip(mins, maxs) for v in pair) if mins is not None else None
    expected = int(header.get("points") or header.get("width") or 0)
    warning = (
        ""
        if not expected or expected == count
        else f"PCD header 点数 {expected}，实际扫描 {count}。"
    )
    return {"bounds": bounds, "warning": warning}


def _decode_pcd_rgb(value: float) -> list[float]:
    import struct

    try:
        integer = int(value)
        if integer == 0 and value != 0:
            integer = struct.unpack("I", struct.pack("f", float(value)))[0]
        r = (integer >> 16) & 255
        g = (integer >> 8) & 255
        b = integer & 255
        return [r / 255.0, g / 255.0, b / 255.0]
    except Exception:
        return [0.2, 0.7, 1.0]


def _iter_numeric_rows(path: Path) -> Iterable[list[float]]:
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",; \t")
        except Exception:
            dialect = csv.excel
            dialect.delimiter = ","
        for row in csv.reader(fh, dialect):
            if len(row) == 1:
                row = row[0].replace(",", " ").split()
            values = []
            for token in row:
                try:
                    values.append(float(token))
                except Exception:
                    pass
            if values:
                yield values


def _sample_vertices(vertices: list[list[float]], max_points: int) -> np.ndarray:
    if not vertices:
        return np.empty((0, 3), dtype=np.float32)
    arr = np.asarray(vertices, dtype=np.float32)
    if len(arr) > max_points:
        idx = np.linspace(0, len(arr) - 1, max_points).astype(np.int64)
        arr = arr[idx]
    return arr


def resource_summary(record: dict) -> str:
    kind = record.get("source_type", "file")
    if kind == "raster":
        return (
            f"{record.get('width', 0)}x{record.get('height', 0)} / {record.get('bands', 0)} bands"
        )
    if kind == "vector":
        return f"{record.get('width', 0)} features / {record.get('dtype', '')}"
    if kind == "pointcloud":
        return f"{record.get('point_count', 0)} points"
    if kind == "mesh":
        return f"{record.get('vertex_count', 0)} vertices / {record.get('face_count', 0)} faces"
    return record.get("format_detail", "")


def resource_type_label(source_type: str) -> str:
    return {
        "raster": "栅格影像",
        "vector": "矢量图层",
        "pointcloud": "点云",
        "mesh": "Mesh模型",
        "model": "模型权重",
        "file": "文件",
    }.get(source_type, source_type)
