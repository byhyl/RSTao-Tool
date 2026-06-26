"""Resource import, classification, and spatial-reference recording."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from common.logger import logger
from core.resource_manager import (
    classify_resource as _classify_resource,
    create_resource_record,
    resource_summary,
    resource_type_label,
    supported_resource_extensions,
)
from core.spatial_reference import (
    compare_spatial_refs,
    compute_file_hash,
    format_spatial_ref,
    read_raster_spatial_ref,
    read_vector_spatial_ref,
)

if TYPE_CHECKING:
    from .app_context import AppContext


class ResourceService:
    """Orchestrates resource import, classification and spatial ref recording."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    # -- import workflow ----------------------------------------------------

    def import_resource(self, path: str, source_type: str | None = None) -> dict | None:
        """Classify path, create resource record, add to open project."""
        ps = self._ctx.project_service
        if not ps.current_project:
            logger.warning("资源导入需要先打开项目")
            return None
        try:
            record = create_resource_record(path, source_type=source_type)
            ps.add_resource(record)
            st = record.get("source_type", source_type or "file")
            if st in {"raster", "vector"}:
                self.record_data_source(path, st)
            ps.mark_dirty()
            return record
        except Exception as exc:
            logger.exception("资源导入失败: %s", exc)
            return None

    def import_resources(self, paths: list[str]) -> list[dict]:
        results: list[dict] = []
        for path in paths:
            r = self.import_resource(path)
            if r:
                results.append(r)
        return results

    # -- classification ----------------------------------------------------

    @staticmethod
    def classify_resource(path: str) -> str:
        return _classify_resource(path)

    @staticmethod
    def supported_extensions() -> tuple[str, ...]:
        return supported_resource_extensions()

    # -- data source recording ----------------------------------------------

    def record_data_source(self, path: str, source_type: str) -> dict | None:
        """Read spatial reference for a data file and add it to the project."""
        ps = self._ctx.project_service
        if not ps.current_project:
            return None

        ref = (
            read_vector_spatial_ref(path)
            if source_type == "vector"
            else read_raster_spatial_ref(path)
        )
        existing = ps.primary_spatial_ref()
        comparison = compare_spatial_refs(existing, ref) if existing else None
        payload = ref.to_dict()
        if comparison:
            payload["comparison"] = comparison
        ps.add_data_source(payload)
        return payload

    def audit_sources_for_paths(self, paths: list[str]) -> list[dict]:
        sources: list[dict] = []
        for path_s in paths:
            try:
                suffix = Path(path_s).suffix.lower()
                if suffix in {".tif", ".tiff", ".img", ".jp2", ".vrt", ".png", ".jpg", ".jpeg", ".bmp"}:
                    sources.append(read_raster_spatial_ref(path_s).to_dict())
                elif suffix == ".shp":
                    sources.append(read_vector_spatial_ref(path_s).to_dict())
                else:
                    sources.append(
                        {
                            "source_path": path_s,
                            "source_type": suffix.lstrip(".") or "file",
                            "file_hash": compute_file_hash(path_s),
                        }
                    )
            except Exception as exc:
                logger.debug("Audit metadata failed for %s: %s", path_s, exc)
        return sources

    # -- static helpers ----------------------------------------------------

    @staticmethod
    def format_spatial_ref(ref) -> str:
        return format_spatial_ref(ref)

    @staticmethod
    def compare(a, b) -> dict | None:
        return compare_spatial_refs(a, b)

    @staticmethod
    def summary(record: dict) -> str:
        return resource_summary(record)

    @staticmethod
    def type_label(source_type: str) -> str:
        return resource_type_label(source_type)
