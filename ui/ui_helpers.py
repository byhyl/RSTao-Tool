"""Small UI helpers shared by CustomTkinter screens."""

import sys
import threading
from pathlib import Path
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

from common.logger import logger
from core.resource_manager import create_resource_record
from core.spatial_reference import (
    compare_spatial_refs,
    compute_file_hash,
    format_spatial_ref,
    read_raster_spatial_ref,
    read_vector_spatial_ref,
)

from .theme import FONT_NORMAL, THEME


def load_ctk_icon(icon_name: str, size: tuple[int, int] = (18, 18)) -> Optional[ctk.CTkImage]:
    """Load an icon from assets/icons as a CTkImage."""
    try:
        base_path = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent.parent
        icon_path = base_path / "assets" / "icons" / f"{icon_name}.png"
        if icon_path.exists():
            return ctk.CTkImage(Image.open(icon_path), size=size)
    except Exception as e:
        logger.debug(f"图标加载失败 {icon_name}: {e}")
    return None


def button_style(kind: str = "secondary") -> dict:
    """Return consistent button styling for common action levels."""
    if kind == "primary":
        return {"fg_color": THEME["accent"], "hover_color": THEME["accent_hover"]}
    if kind == "success":
        return {"fg_color": THEME["success"], "hover_color": THEME["success"]}
    if kind == "danger":
        return {"fg_color": THEME["danger"], "hover_color": THEME["danger"]}
    return {
        "fg_color": "transparent",
        "hover_color": THEME["hover"],
        "border_width": 1,
        "border_color": THEME["border"],
        "text_color": THEME["text_primary"],
    }


def make_button(
    parent, text: str, command: Callable, kind: str = "secondary", icon: str = "", **kwargs
) -> ctk.CTkButton:
    """Create a styled CTkButton with an optional bundled icon."""
    opts = {
        "text": text,
        "command": command,
        "font": FONT_NORMAL,
        "height": 34,
        "corner_radius": 8,
    }
    opts.update(button_style(kind))
    if icon:
        image = load_ctk_icon(icon)
        if image:
            opts["image"] = image
            opts["compound"] = "left"
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def notify(widget, message: str, level: str = "info", timeout: int = 3500):
    """Prefer the app status bar; fall back to modal dialogs only when needed."""
    try:
        top = widget.winfo_toplevel()
        if hasattr(top, "show_status"):
            top.show_status(message, level=level, timeout=timeout)
            return
    except Exception:
        pass

    if level == "error":
        messagebox.showerror("错误", message)
    elif level == "warning":
        messagebox.showwarning("提示", message)


def record_project_result(widget, category: str, title: str, **kwargs):
    """Append a result record to the current project when one is open."""
    try:
        top = widget.winfo_toplevel()
        pm = getattr(top, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None):
            return None
        kwargs["inputs"] = [p for p in kwargs.get("inputs", []) if p]
        kwargs["outputs"] = [p for p in kwargs.get("outputs", []) if p]
        kwargs.setdefault("data_sources", _audit_sources_for_paths(kwargs["inputs"]))
        kwargs.setdefault(
            "input_hashes",
            {
                item["source_path"]: item["file_hash"]
                for item in kwargs["data_sources"]
                if item.get("file_hash")
            },
        )
        kwargs.setdefault(
            "spatial_refs",
            [
                format_spatial_ref(item)
                for item in kwargs["data_sources"]
                if item.get("source_type") in {"raster", "vector"}
            ],
        )
        record = pm.add_result_record(category, title, **kwargs)
        mark_project_dirty(widget)
        return record
    except Exception as e:
        logger.debug(f"记录项目历史失败: {e}")
        return None


def mark_project_dirty(widget):
    """Mark the current project as changed and refresh app chrome when available."""
    try:
        top = widget.winfo_toplevel()
        if hasattr(top, "_mark_project_dirty"):
            top._mark_project_dirty()
            return
        pm = getattr(top, "project_manager", None)
        if pm and getattr(pm, "current_project", None):
            pm.mark_dirty()
    except Exception as e:
        logger.debug(f"项目脏状态更新失败: {e}")


def record_data_source(widget, path: str, source_type: str):
    """Record imported data source spatial/audit metadata in the current project."""
    try:
        top = widget.winfo_toplevel()
        pm = getattr(top, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None):
            return None
        ref = (
            read_vector_spatial_ref(path)
            if source_type == "vector"
            else read_raster_spatial_ref(path)
        )
        existing = pm.primary_spatial_ref()
        comparison = compare_spatial_refs(existing, ref) if existing else None
        payload = ref.to_dict()
        if comparison:
            payload["comparison"] = comparison
            if comparison.get("level") in {"warning", "error"} and hasattr(top, "show_status"):
                top.show_status(
                    comparison.get("message", "空间参考需要确认"), "warning", timeout=6000
                )
        pm.add_data_source(payload)
        try:
            resource = create_resource_record(path, source_type=source_type)
            pm.add_resource(resource)
        except Exception as exc:
            logger.debug(f"记录资源失败: {exc}")
        if hasattr(top, "_update_project_state"):
            top._update_project_state()
        if hasattr(top, "refresh_resource_panel"):
            top.refresh_resource_panel()
        return payload
    except Exception as e:
        logger.debug(f"记录数据源失败: {e}")
        return None


def raster_geo_transform(path: str):
    """Return a viewer-ready raster geotransform, or None when unavailable."""
    try:
        ref = read_raster_spatial_ref(path)
        return ref.transform
    except Exception as e:
        logger.debug(f"Read raster geotransform failed: {e}")
        return None


def _audit_sources_for_paths(paths: list[str]) -> list[dict]:
    sources = []
    for path in paths:
        try:
            suffix = Path(path).suffix.lower()
            if suffix in {".tif", ".tiff", ".img", ".jp2", ".vrt", ".png", ".jpg", ".jpeg", ".bmp"}:
                sources.append(read_raster_spatial_ref(path).to_dict())
            elif suffix == ".shp":
                sources.append(read_vector_spatial_ref(path).to_dict())
            else:
                sources.append(
                    {
                        "source_path": path,
                        "source_type": suffix.lstrip(".") or "file",
                        "file_hash": compute_file_hash(path),
                    }
                )
        except Exception as e:
            logger.debug(f"Audit metadata failed for {path}: {e}")
    return sources


def run_background(widget, work: Callable, on_done: Callable = None, on_error: Callable = None):
    """Run work in a daemon thread and marshal callbacks back to Tk."""

    def _runner():
        try:
            result = work()
            if on_done:
                widget.after(0, lambda: on_done(result))
        except Exception as e:
            logger.error(f"后台任务失败: {e}", exc_info=True)
            if on_error:
                widget.after(0, lambda err=e: on_error(err))
            else:
                widget.after(0, lambda err=e: messagebox.showerror("错误", str(err)))

    threading.Thread(target=_runner, daemon=True).start()
