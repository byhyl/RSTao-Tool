"""Input file inspection helpers used before importing user data."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from common.logger import logger
from core.spatial_reference import (
    format_spatial_ref,
    read_raster_spatial_ref,
    read_vector_spatial_ref,
)
from data.image_io import get_image_metadata


@dataclass
class InspectionResult:
    """Human-readable import preflight result."""

    path: str
    kind: str
    title: str
    summary: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    preview_rows: list[list[str]] = field(default_factory=list)
    can_import: bool = True
    message: str = ""

    def detail_text(self) -> str:
        lines = [self.title, self.path]
        lines.extend(f"{key}: {value}" for key, value in self.summary)
        if self.warnings:
            lines.append("注意:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        if self.preview_rows:
            lines.append("预览:")
            lines.extend(" | ".join(row) for row in self.preview_rows[:5])
        if self.message:
            lines.append(self.message)
        return "\n".join(lines)


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
CSV_EXTS = {".csv", ".txt", ".xy", ".pts"}


def inspect_file(path: str | Path, expected_kind: Optional[str] = None) -> InspectionResult:
    """Inspect a supported file and return user-facing metadata."""
    file_path = Path(path)
    if not file_path.exists():
        return InspectionResult(
            path=str(file_path),
            kind=expected_kind or "unknown",
            title="文件不存在",
            can_import=False,
            message="请选择一个存在的文件。",
        )

    kind = expected_kind or _detect_kind(file_path)
    try:
        if kind == "image":
            return inspect_image(file_path)
        if kind == "csv":
            return inspect_points_file(file_path)
        if kind == "shp":
            return inspect_shapefile(file_path)
        if kind == "onnx":
            return inspect_onnx(file_path)
        if kind == "project":
            return inspect_project(file_path)
    except Exception as exc:
        logger.error(f"输入预检失败: {file_path} ({exc})", exc_info=True)
        return InspectionResult(
            path=str(file_path),
            kind=kind,
            title="预检失败",
            can_import=False,
            message=str(exc),
        )

    return InspectionResult(
        path=str(file_path),
        kind=kind,
        title="未知文件类型",
        can_import=False,
        message="当前文件类型暂不支持导入预检。",
    )


def inspect_image(path: Path) -> InspectionResult:
    meta = get_image_metadata(path)
    spatial_ref = read_raster_spatial_ref(path)
    warnings = []
    if meta["extension"] in (".tif", ".tiff", ".img", ".jp2", ".vrt") and not meta.get("crs"):
        warnings.append("未识别到坐标系信息，后续与矢量数据叠加时需要人工确认 CRS。")
    if meta["size_mb"] >= 500:
        warnings.append("文件较大，加载时可能需要更长时间。")

    return InspectionResult(
        path=str(path),
        kind="image",
        title="影像文件预检",
        summary=[
            ("文件名", meta["name"]),
            ("大小", f"{meta['size_mb']} MB"),
            ("尺寸", f"{meta['width']} x {meta['height']}"),
            ("波段", str(meta["bands"])),
            ("数据类型", meta["dtype"] or "未知"),
            ("驱动", meta["driver"] or "未知"),
            ("坐标系", meta.get("crs") or "未识别"),
            ("EPSG", str(meta.get("epsg") or "未识别")),
            ("空间参考", format_spatial_ref(spatial_ref)),
            ("Hash", spatial_ref.file_hash or "未计算"),
        ],
        warnings=warnings,
    )


def inspect_points_file(path: Path) -> InspectionResult:
    rows = _read_preview_rows(path)
    if not rows:
        return InspectionResult(
            path=str(path),
            kind="csv",
            title="点文件预检",
            can_import=False,
            message="文件为空或无法读取有效行。",
        )

    x_idx, y_idx, has_header = _detect_xy_columns(rows)
    warnings = []
    can_import = True
    if x_idx is None or y_idx is None:
        can_import = False
        warnings.append("未识别到可用的 X/Y 坐标列。")
    elif not has_header:
        warnings.append("未检测到表头，将使用前两列作为 X/Y 坐标。")

    data_rows = rows[1:] if has_header else rows
    valid_points = 0
    if x_idx is not None and y_idx is not None:
        for row in data_rows:
            if len(row) <= max(x_idx, y_idx):
                continue
            try:
                float(row[x_idx])
                float(row[y_idx])
                valid_points += 1
            except ValueError:
                continue

    return InspectionResult(
        path=str(path),
        kind="csv",
        title="点文件预检",
        summary=[
            ("文件名", path.name),
            (
                "坐标列",
                f"{x_idx + 1 if x_idx is not None else '-'} / {y_idx + 1 if y_idx is not None else '-'}",
            ),
            ("识别表头", "是" if has_header else "否"),
            ("有效点数", str(valid_points)),
        ],
        warnings=warnings,
        preview_rows=rows[:5],
        can_import=can_import,
    )


def inspect_shapefile(path: Path) -> InspectionResult:
    import fiona

    spatial_ref = read_vector_spatial_ref(path)

    with fiona.open(path, "r", encoding="utf-8") as src:
        schema = src.schema or {}
        crs = src.crs_wkt or str(src.crs or "")
        feature_count = len(src)
        geom_type = schema.get("geometry", "未知")
        fields = list((schema.get("properties") or {}).keys())

    warnings = []
    if not crs:
        warnings.append("未识别到 CRS，导入后请确认坐标系。")
    if feature_count == 0:
        warnings.append("文件中没有要素。")

    return InspectionResult(
        path=str(path),
        kind="shp",
        title="SHP 文件预检",
        summary=[
            ("文件名", path.name),
            ("要素数量", str(feature_count)),
            ("几何类型", str(geom_type)),
            ("字段", ", ".join(fields[:8]) if fields else "无字段"),
            ("坐标系", crs or "未识别"),
            (
                "范围",
                (
                    ", ".join(f"{v:.3f}" for v in spatial_ref.bounds)
                    if spatial_ref.bounds
                    else "未识别"
                ),
            ),
            ("Hash", spatial_ref.file_hash or "未计算"),
        ],
        warnings=warnings,
    )


def inspect_onnx(path: Path) -> InspectionResult:
    try:
        import onnxruntime as ort
    except ImportError:
        return InspectionResult(
            path=str(path),
            kind="onnx",
            title="ONNX 模型预检",
            can_import=False,
            message="当前环境未安装 onnxruntime，无法加载 ONNX 模型。",
        )

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    return InspectionResult(
        path=str(path),
        kind="onnx",
        title="ONNX 模型预检",
        summary=[
            ("模型", path.name),
            ("输入", "; ".join(f"{item.name}: {item.shape}" for item in inputs) or "无"),
            ("输出", "; ".join(f"{item.name}: {item.shape}" for item in outputs) or "无"),
            ("Provider", ", ".join(session.get_providers())),
        ],
    )


def inspect_project(path: Path) -> InspectionResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return InspectionResult(
        path=str(path),
        kind="project",
        title="项目文件预检",
        summary=[
            ("项目名", str(payload.get("project_name", "未知项目"))),
            ("版本", str(payload.get("schema_version", "未知"))),
            ("创建时间", str(payload.get("created_time", "未知"))),
            ("修改时间", str(payload.get("modified_time", "未知"))),
            ("当前模块", str(payload.get("current_tab", "未知"))),
        ],
    )


def _detect_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in CSV_EXTS:
        return "csv"
    if ext == ".shp":
        return "shp"
    if ext == ".onnx":
        return "onnx"
    if ext == ".rstao":
        return "project"
    return "unknown"


def _read_preview_rows(path: Path, limit: int = 30) -> list[list[str]]:
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample) if "," in sample else csv.excel
        reader = csv.reader(handle, dialect)
        for row in reader:
            if not row:
                continue
            rows.append([cell.strip() for cell in row])
            if len(rows) >= limit:
                break
    return rows


def _detect_xy_columns(rows: Iterable[list[str]]) -> tuple[Optional[int], Optional[int], bool]:
    rows = list(rows)
    header = [cell.strip().lower() for cell in rows[0]]
    x_names = {"x", "lon", "longitude", "easting", "东坐标", "经度"}
    y_names = {"y", "lat", "latitude", "northing", "北坐标", "纬度"}
    x_idx = next((idx for idx, value in enumerate(header) if value in x_names), None)
    y_idx = next((idx for idx, value in enumerate(header) if value in y_names), None)
    if x_idx is not None and y_idx is not None:
        return x_idx, y_idx, True

    if len(rows[0]) >= 2:
        try:
            float(rows[0][0])
            float(rows[0][1])
            return 0, 1, False
        except ValueError:
            pass
    return x_idx, y_idx, False
