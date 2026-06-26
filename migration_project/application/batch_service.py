"""Batch processing orchestration.  Wraps core.batch_processor.BatchProcessor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from core.batch_processor import BatchProcessor, BatchResult

if TYPE_CHECKING:
    from .app_context import AppContext


class BatchService:
    """Orchestrates batch processing workflows."""

    def __init__(self, ctx: AppContext, max_workers: int = 4) -> None:
        self._ctx = ctx
        self._processor = BatchProcessor(max_workers=max_workers)

    def batch_feature_detect(self, input_dir: str, output_dir: str, **kwargs) -> BatchResult:
        return self._processor.batch_feature_detect(input_dir, output_dir, **kwargs)

    def batch_feature_detect_paths(self, image_paths: list[str], output_dir: str, **kwargs) -> BatchResult:
        return self._processor.batch_feature_detect_paths(image_paths, output_dir, **kwargs)

    def batch_match(self, template_path: str, input_dir: str, output_dir: str, **kwargs) -> BatchResult:
        return self._processor.batch_match(template_path, input_dir, output_dir, **kwargs)

    def batch_match_paths(self, template_path: str, image_paths: list[str], output_dir: str, **kwargs) -> BatchResult:
        return self._processor.batch_match_paths(template_path, image_paths, output_dir, **kwargs)

    def batch_image_process(self, input_dir: str, output_dir: str, operator_id: str, **kwargs) -> BatchResult:
        return self._processor.batch_image_process(input_dir, output_dir, operator_id, **kwargs)

    def batch_image_process_paths(self, image_paths: list[str], output_dir: str, operator_id: str, **kwargs) -> BatchResult:
        return self._processor.batch_image_process_paths(image_paths, output_dir, operator_id, **kwargs)

    def export_summary(self, result: BatchResult, output_dir: str, filename_prefix: str = "summary"):
        return self._processor.export_summary(result, output_dir, filename_prefix)

    def iter_images(self, input_dir: str, recursive: bool = False):
        return self._processor.iter_images(input_dir, recursive)

    def collect_images(self, input_dir: str, recursive: bool = False, limit: int = 0) -> list[str]:
        return self._processor.collect_images(input_dir, recursive, limit)

    def on_progress(self, callback: Callable) -> None:
        self._processor.on_progress(callback)

    def on_task_update(self, callback: Callable) -> None:
        self._processor.on_task_update(callback)
