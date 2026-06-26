"""Report generation service.  Wraps core.report_generator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.logger import logger
from core.report_generator import ReportGenerator

if TYPE_CHECKING:
    from .app_context import AppContext


class ReportService:
    """Generates HTML reports and records results in the current project."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    def export_match_report(self, title: str, stats: Any, output_path: str) -> str | None:
        """Generate a match accuracy report and record in project history."""
        ps = self._ctx.project_service
        gen = ReportGenerator()

        project_info = {}
        if ps.current_project:
            project_info = {
                "project_name": ps.current_project.get("project_name", ""),
                "project_path": ps.project_path or "",
            }

        result = gen.generate_match_report(title, stats, output_path, project_info=project_info)
        if result and ps.current_project:
            ps.add_result_record(
                "match_report",
                title,
                output_path=output_path,
                stats=stats.to_dict() if hasattr(stats, "to_dict") else {},
            )
            ps.mark_dirty()
        return result

    def export_feature_report(self, title: str, stats: Any, output_path: str) -> str | None:
        """Generate a feature analysis report and record in project history."""
        ps = self._ctx.project_service
        gen = ReportGenerator()

        project_info = {}
        if ps.current_project:
            project_info = {
                "project_name": ps.current_project.get("project_name", ""),
                "project_path": ps.project_path or "",
            }

        result = gen.generate_feature_report(title, stats, output_path, project_info=project_info)
        if result and ps.current_project:
            ps.add_result_record(
                "feature_report",
                title,
                output_path=output_path,
                stats=stats.to_dict() if hasattr(stats, "to_dict") else {},
            )
            ps.mark_dirty()
        return result
