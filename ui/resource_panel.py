"""Project resource/layer manager panel."""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from core.resource_manager import (
    create_resource_record,
    read_scene_preview,
    resource_summary,
    resource_type_label,
    supported_resource_extensions,
)

from .theme import FONT_NORMAL, FONT_SMALL, PANEL_STYLE, THEME
from .ui_helpers import make_button, notify


class ResourcePanel(ctk.CTkFrame):
    """Left-side project resources and layer manager."""

    def __init__(self, parent, app):
        super().__init__(parent, **PANEL_STYLE)
        self.app = app
        self._item_to_resource = {}
        self._resource_to_item = {}
        self._resource_windows = {}
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            header,
            text="资源管理器",
            font=("Microsoft YaHei UI", 13, "bold"),
            text_color=THEME["text_primary"],
        ).pack(side="left")
        ctk.CTkButton(
            header,
            text="+",
            width=28,
            height=26,
            command=self.import_resources,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
        ).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 6))
        make_button(btn_row, "属性", self.show_properties, width=58, height=28).pack(
            side="left", padx=2
        )
        make_button(btn_row, "预览", self.preview_selected, width=58, height=28).pack(
            side="left", padx=2
        )
        make_button(btn_row, "定位", self.open_location, width=58, height=28).pack(
            side="left", padx=2
        )
        make_button(btn_row, "移除", self.remove_selected, "danger", width=58, height=28).pack(
            side="left", padx=2
        )

        self.tree = ttk.Treeview(
            self,
            columns=("summary",),
            show="tree headings",
            selectmode="browse",
            height=18,
        )
        self.tree.heading("#0", text="资源")
        self.tree.heading("summary", text="摘要")
        self.tree.column("#0", width=150, anchor="w")
        self.tree.column("summary", width=110, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree.bind("<Double-1>", lambda _e: self.preview_selected())

        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure(
            "Treeview",
            background=THEME["card"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["card"],
            borderwidth=0,
            rowheight=24,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["panel"],
            foreground=THEME["text_secondary"],
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", THEME["accent"])])

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._item_to_resource = {}
        self._resource_to_item = {}
        groups = {}
        for resource in self._resources():
            groups.setdefault(resource.get("source_type", "file"), []).append(resource)
        for source_type, resources in groups.items():
            group_id = f"group:{source_type}"
            self.tree.insert(
                "",
                "end",
                iid=group_id,
                text=resource_type_label(source_type),
                values=(f"{len(resources)} 项",),
                open=True,
            )
            for resource in resources:
                rid = resource.get("resource_id") or resource.get("source_path")
                label = self._resource_label(resource)
                item_id = f"res:{rid}"
                self.tree.insert(
                    group_id,
                    "end",
                    iid=item_id,
                    text=label,
                    values=(resource_summary(resource),),
                )
                self._item_to_resource[item_id] = resource
                self._resource_to_item[rid] = item_id

    def import_resources(self):
        patterns = " ".join(f"*{ext}" for ext in supported_resource_extensions())
        paths = filedialog.askopenfilenames(
            title="导入资源",
            filetypes=[
                ("支持的资源", patterns),
                ("栅格影像", "*.tif *.tiff *.img *.jp2 *.vrt *.png *.jpg *.jpeg *.bmp"),
                ("矢量数据", "*.shp *.geojson *.json *.gpkg *.dxf"),
                ("点云", "*.pcd *.las *.laz *.xyz *.txt *.csv *.pts *.ply"),
                ("Mesh模型", "*.obj *.osgb *.ply"),
                ("模型权重", "*.onnx *.pt *.pth *.engine"),
                ("所有文件", "*.*"),
            ],
        )
        for path in paths:
            self.add_path(path)
        if paths:
            self.refresh()

    def add_path(self, path: str, source_type: str | None = None):
        pm = getattr(self.app, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None):
            notify(self, "请先创建或打开项目", "warning")
            return None
        try:
            resource = create_resource_record(path, source_type=source_type)
            pm.add_resource(resource)
            if resource.get("source_type") in {"raster", "vector"}:
                pm.add_data_source(resource)
            self._mark_dirty()
            self.refresh()
            notify(self, f"资源已导入：{Path(path).name}", "success")
            return resource
        except Exception as exc:
            messagebox.showerror("导入资源失败", str(exc))
            return None

    def preview_selected(self):
        resource = self.selected_resource()
        if not resource:
            return
        source_type = resource.get("source_type")
        path = resource.get("source_path", "")
        if source_type == "raster":
            self._preview_raster(path)
        elif source_type == "vector":
            self._switch_vector(path)
        elif source_type in {"pointcloud", "mesh"}:
            self._register_resource_window(resource, ScenePreviewWindow(self, resource))
        else:
            self.show_properties()

    def show_properties(self):
        resource = self.selected_resource()
        if resource:
            self._register_resource_window(resource, ResourcePropertiesWindow(self, resource))

    def open_location(self):
        resource = self.selected_resource()
        if not resource:
            return
        path = Path(resource.get("source_path", ""))
        if path.exists():
            os.startfile(str(path.parent))

    def remove_selected(self):
        resource = self.selected_resource()
        if not resource:
            return
        if not messagebox.askyesno("确认", f"从项目移除资源？\n{resource.get('name', '')}"):
            return
        pm = getattr(self.app, "project_manager", None)
        if pm and pm.remove_resource(resource.get("resource_id", "")):
            self._close_resource_windows(resource)
            self._clear_active_preview(resource)
            self._mark_dirty()
            self.refresh()

    def selected_resource(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._item_to_resource.get(selection[0])

    def _resources(self):
        pm = getattr(self.app, "project_manager", None)
        return pm.get_resources() if pm and getattr(pm, "current_project", None) else []

    def _resource_label(self, resource: dict) -> str:
        prefix = "●" if resource.get("visible", True) else "○"
        warning = " ⚠" if resource.get("warning") else ""
        return f"{prefix} {resource.get('name', '')}{warning}"

    def _preview_raster(self, path: str):
        if hasattr(self.app, "switch_panel"):
            self.app.switch_panel("image_processing")
            panel = getattr(self.app, "current_panel", None)
            if panel and hasattr(panel, "load_image_silent"):
                panel.load_image_silent(path, preview=False)

    def _switch_vector(self, path: str):
        if hasattr(self.app, "switch_panel"):
            self.app.switch_panel("vector")
            panel = getattr(self.app, "current_panel", None)
            if panel and hasattr(panel, "load_shp_direct") and path.lower().endswith(".shp"):
                panel.load_shp_direct(path, preview=False)
            else:
                self.show_properties()

    def _mark_dirty(self):
        if hasattr(self.app, "_mark_project_dirty"):
            self.app._mark_project_dirty()

    def _register_resource_window(self, resource: dict, window):
        resource_id = resource.get("resource_id") or resource.get("source_path")
        if not resource_id:
            return window
        self._resource_windows.setdefault(resource_id, set()).add(window)

        def _close():
            self._resource_windows.get(resource_id, set()).discard(window)
            try:
                window.destroy()
            except Exception:
                pass

        window.protocol("WM_DELETE_WINDOW", _close)
        return window

    def _close_resource_windows(self, resource: dict):
        resource_id = resource.get("resource_id") or resource.get("source_path")
        windows = list(self._resource_windows.pop(resource_id, set()))
        for window in windows:
            try:
                if window.winfo_exists():
                    window.destroy()
            except Exception:
                pass

    def _clear_active_preview(self, resource: dict):
        path = os.path.normcase(os.path.abspath(resource.get("source_path", "")))
        for panel in getattr(self.app, "panels", {}).values():
            try:
                if hasattr(panel, "image_path") and _same_path(panel.image_path, path):
                    panel.image_path = ""
                    panel.original_img = None
                    panel.result_img = None
                    if hasattr(panel, "viewer_original"):
                        panel.viewer_original.clear_image()
                    if hasattr(panel, "viewer_result"):
                        panel.viewer_result.clear_image()
                if hasattr(panel, "reference_path") and _same_path(panel.reference_path, path):
                    panel.reference_path = ""
                    panel.reference_img = None
                    if hasattr(panel, "reference_label"):
                        panel.reference_label.configure(text="参考影像：未加载")
                if hasattr(panel, "search_path") and _same_path(panel.search_path, path):
                    panel.clear_all()
                if hasattr(panel, "base_image_path") and _same_path(panel.base_image_path, path):
                    panel.base_image_path = ""
                    panel.base_image = None
                    if hasattr(panel, "viewer"):
                        panel.viewer.clear_image()
                if hasattr(panel, "layers"):
                    before = len(panel.layers)
                    panel.layers[:] = [
                        layer
                        for layer in panel.layers
                        if not _same_path(layer.get("path", ""), path)
                    ]
                    if len(panel.layers) != before:
                        if hasattr(panel, "_reset_selection"):
                            panel._reset_selection()
                        if hasattr(panel, "refresh_layer_tree"):
                            panel.refresh_layer_tree()
                        if hasattr(panel, "redraw"):
                            panel.redraw()
            except Exception:
                pass


class ResourcePropertiesWindow(ctk.CTkToplevel):
    def __init__(self, parent, resource: dict):
        super().__init__(parent)
        self.title("资源属性")
        self.geometry("520x560")
        self.minsize(420, 360)
        self.configure(fg_color=THEME["bg"])
        self.transient(parent.winfo_toplevel())

        ctk.CTkLabel(
            self,
            text=resource.get("name", "资源"),
            font=("Microsoft YaHei UI", 15, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 8))
        box = ctk.CTkTextbox(
            self,
            font=("Consolas", 11),
            fg_color=THEME["card"],
            text_color=THEME["text_primary"],
            border_width=1,
            border_color=THEME["border"],
            wrap="word",
        )
        box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        lines = []
        for key, value in resource.items():
            if key == "metadata" and not value:
                continue
            lines.append(f"{key}: {value}")
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")


class ScenePreviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, resource: dict):
        super().__init__(parent)
        self.resource = resource
        self.title(f"三维预览 - {resource.get('name', '')}")
        self.geometry("760x620")
        self.minsize(560, 420)
        self.configure(fg_color=THEME["bg"])
        self.transient(parent.winfo_toplevel())
        self._build()

    def _build(self):
        preview = read_scene_preview(self.resource.get("source_path", ""))
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            header,
            text=self.resource.get("name", ""),
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=resource_summary(self.resource),
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        ).pack(side="right")

        if preview.warning:
            ctk.CTkLabel(
                self,
                text=preview.warning,
                font=FONT_SMALL,
                text_color=THEME["warning"],
                wraplength=700,
            ).pack(fill="x", padx=14, pady=(0, 6))

        fig = Figure(figsize=(7, 5), dpi=100, facecolor=THEME["card"])
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor(THEME["card"])
        self._draw_scene(ax, preview)
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=14, pady=(0, 14))
        canvas.draw()

    def _draw_scene(self, ax, preview):
        points = preview.vertices
        if points.size == 0:
            ax.text2D(0.5, 0.5, "暂无可预览的几何数据", transform=ax.transAxes, ha="center")
            return
        points = _normalize_scene(points)
        colors = (
            preview.colors
            if preview.colors is not None and len(preview.colors) == len(points)
            else None
        )
        if preview.faces is not None and len(preview.faces) and len(preview.faces) < 20000:
            valid_faces = preview.faces[np.all(preview.faces < len(points), axis=1)]
            if len(valid_faces):
                poly = Poly3DCollection(points[valid_faces], alpha=0.28)
                poly.set_facecolor((0.2, 0.55, 0.9, 0.28))
                poly.set_edgecolor((0.8, 0.9, 1.0, 0.12))
                ax.add_collection3d(poly)
        sample = points
        if len(sample) > 30000:
            idx = np.linspace(0, len(sample) - 1, 30000).astype(np.int64)
            sample = sample[idx]
            if colors is not None:
                colors = colors[idx]
        ax.scatter(
            sample[:, 0],
            sample[:, 1],
            sample[:, 2],
            s=0.35 if len(sample) > 5000 else 2,
            c=colors if colors is not None else "#4cc9f0",
            depthshade=False,
        )
        mins = sample.min(axis=0)
        maxs = sample.max(axis=0)
        center = (mins + maxs) / 2
        radius = max(float(np.max(maxs - mins)) / 2, 1e-6)
        ax.set_xlim(center[0] - radius, center[0] + radius)
        ax.set_ylim(center[1] - radius, center[1] + radius)
        ax.set_zlim(center[2] - radius, center[2] + radius)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")


def _normalize_scene(points: np.ndarray) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float32)
    if arr.size == 0:
        return arr.reshape(0, 3)
    center = np.nanmean(arr[:, :3], axis=0)
    arr = arr[:, :3] - center
    scale = np.nanmax(np.linalg.norm(arr, axis=1))
    if np.isfinite(scale) and scale > 0:
        arr = arr / scale
    return arr


def _same_path(value: str, normalized_path: str) -> bool:
    if not value or not normalized_path:
        return False
    try:
        return os.path.normcase(os.path.abspath(value)) == normalized_path
    except Exception:
        return False
