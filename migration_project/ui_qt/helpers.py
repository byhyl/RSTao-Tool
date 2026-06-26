"""Qt-specific UI helpers — replaces ui/ui_helpers.py for the migration project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMessageBox, QStatusBar, QWidget


def notify(widget: QWidget, message: str, level: str = "info",
           timeout: int = 5000) -> None:
    """Show a notification via status bar or message box."""
    window = widget.window()
    if window and hasattr(window, "statusBar"):
        sb = window.statusBar()
        if isinstance(sb, QStatusBar):
            sb.showMessage(message, timeout)
            return
    if level == "error":
        QMessageBox.critical(widget, "Error", message)
    elif level == "warning":
        QMessageBox.warning(widget, "Warning", message)
    else:
        QMessageBox.information(widget, "Info", message)


def mark_project_dirty(main_window: Any) -> None:
    """Mark the current project as modified."""
    if hasattr(main_window, "_ctx"):
        main_window._ctx.project_service.mark_dirty()


def record_project_result(main_window: Any, category: str, title: str,
                          **kwargs: Any) -> dict | None:
    """Record a processing result in the current project's history."""
    if hasattr(main_window, "_ctx"):
        return main_window._ctx.project_service.add_result_record(
            category, title, **kwargs
        )
    return None


def record_data_source(main_window: Any, path: str, source_type: str) -> None:
    """Record a data source's spatial metadata in the project."""
    if hasattr(main_window, "_ctx"):
        main_window._ctx.resource_service.record_data_source(path, source_type)


def raster_geo_transform(path: str) -> tuple | None:
    """Get geotransform for a raster file."""
    from core.spatial_reference import read_raster_spatial_ref
    sr = read_raster_spatial_ref(str(path))
    if sr and sr.transform:
        return sr.transform
    return None
