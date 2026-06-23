"""Integrated 3D viewer tab.

The tab uses PyVista/VTK as the embedded rendering surface and keeps Open3D
limited to geometry operations. This avoids mixing two GUI event loops inside
the main CustomTkinter window.
"""

from __future__ import annotations

import math
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
import numpy as np

from common.logger import logger
from core.gpu_accel import (
    clear_gpu_status_cache,
    format_gpu_setup_plan,
    get_gpu_setup_plan,
    get_gpu_status,
)
from core.mesh_ops import load_mesh as o3d_load_mesh
from core.pointcloud_io import export_las, export_ply
from core.pointcloud_ops import (
    PointCloudData,
    build_classification_colors,
    classify_ground,
    clip_by_plane_data,
    crop_by_bounds_data,
    estimate_normals_data,
    local_roughness_curvature,
    nearest_point,
    normalize_height,
    pointcloud_to_grids,
    radius_outlier_removal_data,
    smrf_filter_data,
    statistical_outlier_removal_data,
    to_o3d_pointcloud,
    voxel_downsample_data,
)
from core.resource_manager import read_scene_preview
from core.scene_graph import ColorMode, LayerType, SceneGraph, SceneLayer, apply_colormap
from core.terrain_analysis import hillshade

from .theme import FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME
from .ui_helpers import make_button
from .viewer_3d_lod import LODManager
from .viewer_3d_tasks import Viewer3DTask, Viewer3DTaskProgress, Viewer3DTaskResult

pv = None
_PV_AVAILABLE: bool | None = None

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    Image = None
    _PIL_AVAILABLE = False


_POINT_CHUNK_SIZE = 500_000
_MAX_POINTS_IN_MEMORY = 3_000_000
_MAX_RENDER_POINTS = 300_000
_MAX_DEM_CELLS = 1_000_000
_QUALITY_BUDGETS = {"流畅": 150_000, "均衡": 300_000, "精细": 800_000}


class Viewer3DTab(ctk.CTkFrame):
    """3D viewer tab backed by project resources."""

    def __init__(self, parent, status_vars=None, app=None):
        super().__init__(parent, fg_color=THEME["bg"])
        self.app = app
        self.status_vars = status_vars or {}
        self.scene = SceneGraph()
        self.lod_mgr = LODManager(max_points_per_frame=_MAX_RENDER_POINTS)
        self._loading = False
        self._pv_plotter = None
        self._pv_label = None
        self._pv_drag: tuple[int, int] | None = None
        self._pv_ctk_img = None
        self._renderer_label = None
        self._pending_restore_layers: list[dict] = []
        self._restore_clear_pending = False
        self._task: Viewer3DTask | None = None
        self._history: list[dict[str, str]] = []
        self._render_budget = _MAX_RENDER_POINTS
        self._cm_var = ctk.StringVar(value="rgb")
        self._quality_var = ctk.StringVar(value="均衡")
        self._gpu_var = ctk.BooleanVar(value=False)
        self._voxel_var = ctk.StringVar(value="0.5")
        self._sor_neighbors_var = ctk.StringVar(value="20")
        self._sor_std_var = ctk.StringVar(value="2.0")
        self._radius_var = ctk.StringVar(value="1.0")
        self._radius_neighbors_var = ctk.StringVar(value="12")
        self._ground_cell_var = ctk.StringVar(value="1.0")
        self._ground_height_var = ctk.StringVar(value="0.5")
        self._dem_cell_var = ctk.StringVar(value="1.0")
        self._normal_radius_var = ctk.StringVar(value="0.0")
        self._normal_nn_var = ctk.StringVar(value="30")
        self._roughness_k_var = ctk.StringVar(value="12")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=300)
        self.grid_columnconfigure(1, weight=4)
        self._build_left()
        self._build_right()

    # ---------- UI ----------

    def _build_left(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, **PANEL_STYLE)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(
            scroll, text="3D 工作台", font=FONT_SUBTITLE, text_color=THEME["text_primary"]
        ).pack(anchor="w", padx=4, pady=(8, 6))

        resource_box = self._section(scroll, "项目资源")
        self._res_list = ctk.CTkScrollableFrame(resource_box, fg_color="transparent", height=120)
        self._res_list.pack(fill="x", padx=0, pady=(2, 4))
        resource_actions = ctk.CTkFrame(resource_box, fg_color="transparent")
        resource_actions.pack(fill="x", pady=(2, 0))
        make_button(resource_actions, "刷新", self._refresh_resources, width=76, height=26).pack(
            side="left", padx=(0, 6)
        )
        make_button(
            resource_actions, "加载到3D", self._load_first_resource, "primary", width=96, height=26
        ).pack(side="left")

        status_box = self._section(scroll, "状态")
        self._prog = ctk.CTkProgressBar(status_box, width=240)
        self._prog.pack(fill="x", pady=(2, 4))
        self._prog.set(0.0)
        self._prog_lbl = ctk.CTkLabel(
            status_box, text="就绪", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        self._prog_lbl.pack(anchor="w")
        self._pt_lbl = ctk.CTkLabel(
            status_box, text="", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        self._pt_lbl.pack(anchor="w", pady=(2, 0))
        self._gpu_status_lbl = ctk.CTkLabel(
            status_box, text="", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        self._gpu_status_lbl.pack(anchor="w", pady=(2, 0))

        layer_box = self._section(scroll, "图层")
        self._layer_list = ctk.CTkScrollableFrame(layer_box, fg_color="transparent", height=130)
        self._layer_list.pack(fill="x", pady=(2, 2))

        view_box = self._section(scroll, "显示")
        self._quality_menu = ctk.CTkOptionMenu(
            view_box,
            values=list(_QUALITY_BUDGETS),
            variable=self._quality_var,
            command=self._set_quality,
            width=120,
            height=26,
            font=FONT_SMALL,
        )
        self._quality_menu.pack(anchor="w", pady=(0, 4))
        for label, mode in [
            ("RGB", "rgb"),
            ("分类", "classification"),
            ("高程", "elevation"),
            ("强度", "intensity"),
            ("法线", "normal"),
        ]:
            ctk.CTkRadioButton(
                view_box,
                text=label,
                variable=self._cm_var,
                value=mode,
                font=FONT_SMALL,
                command=lambda m=mode: self._on_color_mode(m),
            ).pack(anchor="w", pady=1)

        accel_box = self._section(scroll, "计算")
        ctk.CTkCheckBox(
            accel_box,
            text="GPU 加速",
            variable=self._gpu_var,
            command=lambda: self._refresh_gpu_status(prompt=True),
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(0, 4))
        gpu_row = ctk.CTkFrame(accel_box, fg_color="transparent")
        gpu_row.pack(fill="x", pady=(0, 4))
        make_button(gpu_row, "检测/修复GPU", self._show_gpu_setup, width=118, height=26).pack(
            side="left", padx=(0, 6)
        )
        make_button(gpu_row, "重新检测", self._redetect_gpu, width=82, height=26).pack(side="left")

        proc_box = self._section(scroll, "处理")
        self._button_grid(
            proc_box,
            [
                ("体素下采样", self._voxel),
                ("统计去噪", self._sorf),
                ("半径去噪", self._radius_filter),
                ("地面分类", self._csf),
                ("高度归一", self._normalize_height),
                ("估计法线", self._estimate_normals),
                ("粗糙/曲率", self._roughness_curvature),
                ("裁剪包围盒", self._crop_to_bbox_center),
                ("剖切Z中位", self._clip_z_median),
                ("生成DEM/DSM", self._generate_dem_dsm),
                ("点拾取", self._pick_center_point),
                ("取消任务", self._cancel_task),
            ],
        )

        history_box = self._section(scroll, "任务历史")
        self._history_list = ctk.CTkScrollableFrame(history_box, fg_color="transparent", height=120)
        self._history_list.pack(fill="x", pady=(2, 0))

        export_box = self._section(scroll, "导出")
        export_row = ctk.CTkFrame(export_box, fg_color="transparent")
        export_row.pack(fill="x")
        make_button(export_row, "LAS", self._export_las, width=50, height=24).pack(
            side="left", padx=2
        )
        make_button(export_row, "PLY", self._export_ply, width=50, height=24).pack(
            side="left", padx=2
        )
        make_button(export_row, "截图", self._export_shot, width=50, height=24).pack(
            side="left", padx=2
        )
        make_button(export_row, "清除", self._clear_all, "danger", width=50, height=24).pack(
            side="left", padx=2
        )
        self._refresh_gpu_status()
        self._refresh_history()

    def _build_right(self) -> None:
        right = ctk.CTkFrame(self, fg_color=THEME["bg"], corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(right, fg_color=THEME["panel"], corner_radius=6)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for text, cmd in [
            ("复位", self._reset_camera),
            ("俯视", lambda: self._set_camera_view("xy")),
            ("前视", lambda: self._set_camera_view("xz")),
            ("侧视", lambda: self._set_camera_view("yz")),
            ("截图", self._export_shot),
        ]:
            ctk.CTkButton(
                toolbar,
                text=text,
                width=58,
                height=26,
                font=FONT_SMALL,
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=cmd,
            ).pack(side="left", padx=3, pady=5)
        self._viewport_status = ctk.CTkLabel(
            toolbar,
            text="视图就绪",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        )
        self._viewport_status.pack(side="right", padx=8)

        self._vp = ctk.CTkFrame(right, fg_color="#1a1a1f", corner_radius=0)
        self._vp.grid(row=1, column=0, sticky="nsew")
        self._renderer_label = ctk.CTkLabel(
            self._vp,
            text="选择资源后初始化3D视图",
            font=FONT_SUBTITLE,
            text_color=THEME["text_muted"],
        )
        self._renderer_label.place(relx=0.5, rely=0.5, anchor="center")

    def _section(self, parent, title: str) -> ctk.CTkFrame:
        ctk.CTkLabel(parent, text=title, font=FONT_SMALL, text_color=THEME["text_secondary"]).pack(
            anchor="w", padx=4, pady=(10, 3)
        )
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=4, pady=(0, 2))
        return frame

    def _param_row(self, parent, label: str, var: ctk.StringVar, unit: str = "") -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row,
            text=label,
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
            width=70,
            anchor="w",
        ).pack(side="left")
        ctk.CTkEntry(row, textvariable=var, width=72, height=24, font=FONT_SMALL).pack(
            side="left", padx=(4, 4)
        )
        if unit:
            ctk.CTkLabel(row, text=unit, font=FONT_SMALL, text_color=THEME["text_muted"]).pack(
                side="left"
            )

    def _button_grid(self, parent, items: list[tuple[str, Callable]]) -> None:
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x")
        for index, (text, cmd) in enumerate(items):
            row = index // 2
            col = index % 2
            btn = ctk.CTkButton(
                grid,
                text=text,
                height=26,
                width=116,
                font=FONT_SMALL,
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                border_width=1,
                border_color=THEME["border"],
                command=cmd,
            )
            btn.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
        grid.grid_columnconfigure((0, 1), weight=1)

    def _show_algorithm_dialog(
        self,
        title: str,
        fields: list[dict],
        *,
        include_backend: bool = False,
        include_output: bool = True,
    ) -> dict | None:
        result: dict | None = None
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.configure(fg_color=THEME["bg"])
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        body = ctk.CTkFrame(dialog, fg_color=THEME["panel"], corner_radius=8)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            body,
            text=title,
            font=FONT_SUBTITLE,
            text_color=THEME["text_primary"],
        ).pack(anchor="w", pady=(0, 10))

        field_vars: dict[str, ctk.StringVar] = {}
        first_entry = None
        for spec in fields:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=spec["label"],
                width=88,
                font=FONT_SMALL,
                text_color=THEME["text_secondary"],
                anchor="w",
            ).pack(side="left")
            default = spec.get("default", "")
            source_var = spec.get("var")
            if source_var is not None:
                default = source_var.get()
            value_var = ctk.StringVar(value=str(default))
            field_vars[spec["key"]] = value_var
            if spec.get("type") == "choice":
                ctk.CTkOptionMenu(
                    row,
                    values=list(spec.get("values", [])),
                    variable=value_var,
                    width=128,
                    height=26,
                    font=FONT_SMALL,
                ).pack(side="left", padx=(4, 4))
            else:
                entry = ctk.CTkEntry(row, textvariable=value_var, width=128, height=26)
                entry.pack(side="left", padx=(4, 4))
                first_entry = first_entry or entry
            unit = spec.get("unit", "")
            if unit:
                ctk.CTkLabel(
                    row,
                    text=unit,
                    font=FONT_SMALL,
                    text_color=THEME["text_muted"],
                ).pack(side="left")

        backend_var = ctk.StringVar(value="GPU" if self._gpu_var.get() else "自动")
        if include_backend:
            self._dialog_option_row(body, "计算后端", backend_var, ["自动", "CPU", "GPU"])

        output_var = ctk.StringVar(value="新图层")
        if include_output:
            self._dialog_option_row(body, "输出", output_var, ["新图层", "覆盖当前"])

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(14, 0))

        def _cancel() -> None:
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        def _submit() -> None:
            nonlocal result
            params: dict[str, int | float | str] = {}
            try:
                for spec in fields:
                    key = spec["key"]
                    raw = field_vars[key].get()
                    value_type = spec.get("type", "float")
                    if value_type == "choice":
                        value = raw
                    elif value_type == "int":
                        value = int(float(raw))
                    else:
                        value = float(raw)
                    minimum = spec.get("min")
                    maximum = spec.get("max")
                    if minimum is not None and value < minimum:
                        value = minimum
                    if maximum is not None and value > maximum:
                        value = maximum
                    params[key] = value
                    source_var = spec.get("var")
                    if source_var is not None:
                        source_var.set(f"{value:g}" if isinstance(value, float) else str(value))
            except (TypeError, ValueError):
                messagebox.showerror(title, "参数格式不正确，请检查数值输入。")
                return
            result = {
                "params": params,
                "backend_choice": backend_var.get() if include_backend else "CPU",
                "output_mode": "new" if output_var.get() == "新图层" else "replace",
                "output_label": output_var.get() if include_output else "覆盖当前",
            }
            _cancel()

        make_button(actions, "取消", _cancel, width=72, height=28).pack(side="right", padx=(6, 0))
        make_button(actions, "开始", _submit, "primary", width=82, height=28).pack(side="right")

        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + 90
        dialog.geometry(f"+{x}+{y}")
        if first_entry is not None:
            first_entry.focus_set()
        self.wait_window(dialog)
        return result

    def _dialog_option_row(
        self, parent, label: str, variable: ctk.StringVar, values: list[str]
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(
            row,
            text=label,
            width=88,
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
            anchor="w",
        ).pack(side="left")
        ctk.CTkOptionMenu(
            row,
            values=values,
            variable=variable,
            width=128,
            height=26,
            font=FONT_SMALL,
        ).pack(side="left", padx=(4, 4))

    def on_show(self) -> None:
        self._refresh_resources()
        self._restore_pending_layers()

    # ---------- Resources ----------

    def _refresh_resources(self) -> None:
        for widget in self._res_list.winfo_children():
            widget.destroy()
        resources = self._get_3d_resources()
        if not resources:
            ctk.CTkLabel(
                self._res_list, text="无3D资源", font=FONT_SMALL, text_color=THEME["text_muted"]
            ).pack(padx=4, pady=8)
            return
        for resource in resources:
            name = resource.get("name", "?")
            ctk.CTkButton(
                self._res_list,
                text=name,
                width=180,
                height=22,
                font=FONT_SMALL,
                anchor="w",
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=lambda r=resource: self._load_resource(r),
            ).pack(anchor="w", padx=2, pady=1)

    def _get_3d_resources(self) -> list[dict]:
        if not self.app:
            return []
        pm = getattr(self.app, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None):
            return []
        return [
            r
            for r in pm.get_resources()
            if r.get("source_type") in ("pointcloud", "mesh", "raster")
        ]

    def _load_first_resource(self) -> None:
        resources = self._get_3d_resources()
        if resources:
            self._load_resource(resources[0])

    def _load_resource(self, resource: dict, layer_state: dict | None = None) -> None:
        if not self._ensure_renderer():
            return
        path = resource.get("source_path", "")
        source_type = resource.get("source_type", "")
        if source_type == "pointcloud":
            self._load_pc(path, layer_state=layer_state)
        elif source_type == "mesh":
            self._load_mesh(path, layer_state=layer_state)
        elif source_type == "raster":
            self._load_dem(path, layer_state=layer_state)

    def _restore_pending_layers(self) -> None:
        if not self._pending_restore_layers or self._loading:
            return
        if not self._ensure_renderer():
            return
        if self._restore_clear_pending:
            self.scene.clear()
            self.lod_mgr.clear()
            self._refresh_layers()
            self._restore_clear_pending = False
        layer_state = self._pending_restore_layers.pop(0)
        path = layer_state.get("source_path", "")
        if not path or not Path(path).exists():
            placeholder = SceneLayer.from_dict(layer_state)
            placeholder.warning = placeholder.warning or "源文件不存在，无法恢复几何"
            self.scene.add_layer(placeholder)
            self._refresh_layers()
            self.after(0, self._restore_pending_layers)
            return
        self._load_resource(
            {
                "source_path": path,
                "source_type": self._source_type_from_layer_state(layer_state),
            },
            layer_state=layer_state,
        )

    @staticmethod
    def _source_type_from_layer_state(layer_state: dict) -> str:
        layer_type = layer_state.get("layer_type", "")
        if layer_type == LayerType.DEM.value:
            return "raster"
        if layer_type == LayerType.MESH.value:
            return "mesh"
        return "pointcloud"

    @staticmethod
    def _apply_serialized_layer_state(layer: SceneLayer, layer_state: dict | None) -> None:
        if not layer_state:
            return
        layer.id = layer_state.get("id") or layer.id
        layer.name = layer_state.get("name") or layer.name
        layer.visible = bool(layer_state.get("visible", layer.visible))
        layer.opacity = float(layer_state.get("opacity", layer.opacity))
        layer.locked = bool(layer_state.get("locked", layer.locked))
        layer.order = int(layer_state.get("order", layer.order))
        layer.point_size = float(layer_state.get("point_size", layer.point_size))
        layer.colormap = layer_state.get("colormap", layer.colormap)
        layer.warning = layer_state.get("warning", layer.warning)
        if layer_state.get("crs"):
            layer.crs = layer_state["crs"]
        if layer_state.get("epsg") is not None:
            layer.epsg = layer_state["epsg"]
        try:
            layer.color_mode = ColorMode(layer_state.get("color_mode", layer.color_mode.value))
        except ValueError:
            pass
        if "single_color" in layer_state:
            layer.single_color = tuple(layer_state["single_color"])
        if isinstance(layer_state.get("metadata"), dict):
            layer.metadata.update(layer_state["metadata"])

    # ---------- Loading ----------

    def _load_pc(self, path: str, layer_state: dict | None = None) -> None:
        if not self._begin_load(path):
            return
        name = Path(path).name
        self._set_progress(0.0, f"加载点云: {name}")

        def _do() -> None:
            try:
                layer = self._read_pointcloud_layer(path, name, layer_state=layer_state)
                self.after(0, self._on_layer_loaded, layer)
            except Exception as exc:
                logger.error("Point cloud load failed: %s", exc, exc_info=True)
                self.after(0, lambda: messagebox.showerror("点云加载失败", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _read_pointcloud_layer(
        self, path: str, name: str, layer_state: dict | None = None
    ) -> SceneLayer:
        suffix = path.lower()
        pts_list: list[np.ndarray] = []
        clr_list: list[np.ndarray] = []
        cls_list: list[np.ndarray] = []
        intensity_list: list[np.ndarray] = []
        source_total = 0
        sampled = False

        if suffix.endswith((".las", ".laz")):
            import laspy

            with laspy.open(path) as las_file:
                source_total = int(las_file.header.point_count)
                stride = max(1, math.ceil(source_total / _MAX_POINTS_IN_MEMORY))
                sampled = stride > 1
                crs = ""
                try:
                    parsed_crs = las_file.header.parse_crs()
                    crs = parsed_crs.to_wkt() if parsed_crs else ""
                except Exception:
                    crs = ""

                for index, chunk in enumerate(las_file.chunk_iterator(_POINT_CHUNK_SIZE)):
                    points = np.column_stack(
                        [
                            np.asarray(chunk.x, dtype=np.float64),
                            np.asarray(chunk.y, dtype=np.float64),
                            np.asarray(chunk.z, dtype=np.float64),
                        ]
                    )
                    if stride > 1:
                        points = points[::stride]
                    pts_list.append(points)

                    if hasattr(chunk, "red") and len(points):
                        colors = np.column_stack(
                            [
                                np.asarray(chunk.red, dtype=np.float32) / 65535.0,
                                np.asarray(chunk.green, dtype=np.float32) / 65535.0,
                                np.asarray(chunk.blue, dtype=np.float32) / 65535.0,
                            ]
                        )
                        clr_list.append(colors[::stride] if stride > 1 else colors)

                    if hasattr(chunk, "classification") and len(points):
                        classes = np.asarray(chunk.classification, dtype=np.int32)
                        cls_list.append(classes[::stride] if stride > 1 else classes)

                    if hasattr(chunk, "intensity") and len(points):
                        intensities = np.asarray(chunk.intensity, dtype=np.float32)
                        intensity_list.append(intensities[::stride] if stride > 1 else intensities)

                    progress = min(1.0, (index + 1) * _POINT_CHUNK_SIZE / max(source_total, 1))
                    self.after(0, self._set_progress, progress, f"加载点云: {name} {progress:.0%}")
        else:
            preview = read_scene_preview(path, max_points=_MAX_POINTS_IN_MEMORY)
            if preview.vertices.size == 0:
                raise ValueError(preview.warning or "点云为空或暂不支持预览")
            pts_list.append(preview.vertices.astype(np.float64))
            if preview.colors is not None:
                clr_list.append(np.asarray(preview.colors, dtype=np.float64))
            source_total = len(preview.vertices)

        if not pts_list:
            raise ValueError("点云为空")

        points = np.vstack(pts_list)
        colors = np.vstack(clr_list) if clr_list else None
        classes = np.concatenate(cls_list) if cls_list else None
        intensities = np.concatenate(intensity_list) if intensity_list else None

        pcd = to_o3d_pointcloud(points, colors)
        layer = SceneLayer(
            name=Path(path).stem,
            layer_type=LayerType.POINT_CLOUD,
            source_path=path,
            geometry=pcd,
            point_count=len(points),
            crs=locals().get("crs", ""),
            metadata={
                "source_point_count": source_total,
                "loaded_point_count": len(points),
                "sampled": sampled,
            },
        )
        if classes is not None and len(classes) == len(points):
            layer.attributes["classification"] = classes
        if intensities is not None and len(intensities) == len(points):
            layer.attributes["intensity"] = intensities
        self._apply_serialized_layer_state(layer, layer_state)
        self.lod_mgr.build(layer.id, points, colors=colors, classifications=classes)
        return layer

    def _load_mesh(self, path: str, layer_state: dict | None = None) -> None:
        if not self._begin_load(path):
            return
        self._set_progress(0.0, f"加载Mesh: {Path(path).name}")

        def _do() -> None:
            try:
                mesh = o3d_load_mesh(path)
                vertices = np.asarray(mesh.vertices)
                triangles = np.asarray(mesh.triangles)
                layer_type = LayerType.MESH if len(triangles) else LayerType.POINT_CLOUD
                geometry = mesh if layer_type == LayerType.MESH else to_o3d_pointcloud(vertices)
                layer = SceneLayer(
                    name=Path(path).stem,
                    layer_type=layer_type,
                    source_path=path,
                    geometry=geometry,
                    point_count=len(vertices),
                    face_count=len(triangles),
                )
                self._apply_serialized_layer_state(layer, layer_state)
                self.after(0, self._on_layer_loaded, layer)
            except Exception as exc:
                logger.error("Mesh load failed: %s", exc, exc_info=True)
                self.after(0, lambda: messagebox.showerror("Mesh加载失败", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _load_dem(self, path: str, layer_state: dict | None = None) -> None:
        if not self._begin_load(path):
            return
        self._set_progress(0.0, f"加载DEM: {Path(path).name}")

        def _do() -> None:
            try:
                import rasterio

                with rasterio.open(path) as ds:
                    dem = ds.read(1).astype(np.float32)
                    nodata = ds.nodata
                    if nodata is not None:
                        dem[dem == nodata] = np.nan
                    transform = ds.transform
                    crs = ds.crs.to_wkt() if ds.crs else ""

                rows, cols = dem.shape
                stride = max(1, math.ceil(math.sqrt((rows * cols) / _MAX_DEM_CELLS)))
                dem_sample = dem[::stride, ::stride]
                valid_mean = float(np.nanmean(dem_sample)) if np.isfinite(dem_sample).any() else 0.0
                zz = np.nan_to_num(dem_sample, nan=valid_mean)

                sample_rows = np.arange(0, rows, stride, dtype=np.float64)
                sample_cols = np.arange(0, cols, stride, dtype=np.float64)
                cc, rr = np.meshgrid(sample_cols + 0.5, sample_rows + 0.5)
                xx = transform.c + cc * transform.a + rr * transform.b
                yy = transform.f + cc * transform.d + rr * transform.e
                points = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

                cell_size = max(abs(float(transform.a)), abs(float(transform.e)), 1e-6) * stride
                shade = hillshade(np.nan_to_num(dem_sample, nan=valid_mean), cell_size=cell_size)
                colors = np.column_stack([shade.ravel()] * 3).astype(np.float64)
                pcd = to_o3d_pointcloud(points, colors)
                layer = SceneLayer(
                    name=Path(path).stem,
                    layer_type=LayerType.DEM,
                    source_path=path,
                    geometry=pcd,
                    point_count=len(points),
                    crs=crs,
                    color_mode=ColorMode.ELEVATION,
                    metadata={
                        "source_cells": rows * cols,
                        "loaded_cells": len(points),
                        "sampled": stride > 1,
                        "dem_stride": stride,
                    },
                )
                self._apply_serialized_layer_state(layer, layer_state)
                self.after(0, self._on_layer_loaded, layer)
            except Exception as exc:
                logger.error("DEM load failed: %s", exc, exc_info=True)
                self.after(0, lambda: messagebox.showerror("DEM加载失败", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _begin_load(self, path: str) -> bool:
        if self._loading:
            return False
        if not path or not Path(path).exists():
            messagebox.showerror("加载失败", f"文件不存在: {path}")
            return False
        self._loading = True
        return True

    def _on_layer_loaded(self, layer: SceneLayer) -> None:
        self.scene.add_layer(layer)
        self._refresh_layers()
        self._refresh_point_count()
        self._render_layer(layer, reset_camera=True)
        self._set_progress(1.0, self._layer_status(layer))
        if self._pending_restore_layers:
            self.after(100, self._restore_pending_layers)

    # ---------- PyVista rendering ----------

    def _init_pv_canvas(self) -> None:
        global pv, _PV_AVAILABLE
        if self._pv_plotter is not None:
            return
        if _PV_AVAILABLE is None:
            try:
                import pyvista as _pv

                pv = _pv
                _PV_AVAILABLE = True
            except ImportError:
                _PV_AVAILABLE = False
        if not _PV_AVAILABLE or not _PIL_AVAILABLE:
            msg = "PyVista/Pillow 不可用，无法显示3D视图"
            ctk.CTkLabel(
                self._vp, text=msg, font=FONT_SUBTITLE, text_color=THEME["text_muted"]
            ).place(relx=0.5, rely=0.5, anchor="center")
            self._set_progress(0.0, msg)
            return
        try:
            if self._renderer_label is not None and self._renderer_label.winfo_exists():
                self._renderer_label.destroy()
                self._renderer_label = None
            self._pv_plotter = pv.Plotter(off_screen=True, window_size=[900, 650])
            self._pv_plotter.set_background("#1a1a26")
            self._pv_plotter.show_axes()
            self._pv_label = ctk.CTkLabel(self._vp, text="")
            self._pv_label.pack(fill="both", expand=True)
            self._pv_label.bind("<Button-1>", self._on_canvas_press)
            self._pv_label.bind("<B1-Motion>", self._on_canvas_drag)
            self._pv_label.bind("<MouseWheel>", self._on_canvas_scroll)
            self._render_pv()
        except Exception as exc:
            logger.error("PyVista init failed: %s", exc, exc_info=True)
            self._set_progress(0.0, f"3D初始化失败: {exc}")

    def _ensure_renderer(self) -> bool:
        if self._pv_plotter is None:
            self._set_progress(0.0, "正在初始化3D渲染器...")
            self._init_pv_canvas()
        return self._pv_plotter is not None

    def _render_layer(self, layer: SceneLayer, reset_camera: bool = False) -> None:
        if self._pv_plotter is None:
            return
        try:
            self._pv_plotter.remove_actor(layer.id, reset_camera=False)
        except Exception:
            pass
        if not layer.visible or not layer.has_geometry:
            self._render_pv()
            return
        if layer.layer_type in (LayerType.POINT_CLOUD, LayerType.DEM):
            self._add_point_layer(layer)
        elif layer.layer_type == LayerType.MESH:
            self._add_mesh_layer(layer)
        if reset_camera:
            self._pv_plotter.reset_camera()
        self._render_pv()

    def _add_point_layer(self, layer: SceneLayer) -> None:
        points = np.asarray(layer.geometry.points, dtype=np.float64)
        if points.size == 0:
            return
        indices = self._render_indices(len(points))
        render_points = points[indices]
        colors = self._compute_colors(layer, points)
        render_colors = (
            colors[indices] if colors is not None and len(colors) == len(points) else None
        )
        cloud = pv.PolyData(render_points[:, :3])
        if render_colors is not None:
            rgb = np.clip(render_colors[:, :3] * 255, 0, 255).astype(np.uint8)
            cloud["_rgb"] = rgb
            self._pv_plotter.add_mesh(
                cloud,
                scalars="_rgb",
                rgb=True,
                point_size=max(1.0, float(layer.point_size)),
                render_points_as_spheres=False,
                name=layer.id,
            )
        else:
            self._pv_plotter.add_mesh(
                cloud,
                color="#4cc9f0",
                point_size=max(1.0, float(layer.point_size)),
                render_points_as_spheres=False,
                name=layer.id,
            )

    def _add_mesh_layer(self, layer: SceneLayer) -> None:
        vertices = np.asarray(layer.geometry.vertices, dtype=np.float64)
        triangles = np.asarray(layer.geometry.triangles, dtype=np.int64)
        if vertices.size == 0:
            return
        if triangles.size == 0:
            cloud = pv.PolyData(vertices[:, :3])
            self._pv_plotter.add_mesh(
                cloud,
                color="#4cc9f0",
                point_size=max(1.0, float(layer.point_size)),
                render_points_as_spheres=False,
                name=layer.id,
            )
            return
        faces = np.column_stack([np.full(len(triangles), 3, dtype=np.int64), triangles]).ravel()
        mesh = pv.PolyData(vertices, faces)
        self._pv_plotter.add_mesh(mesh, color="#6bb5d0", show_edges=False, name=layer.id)

    def _render_pv(self) -> None:
        if self._pv_plotter is None or self._pv_label is None:
            return
        try:
            width = max(64, self._vp.winfo_width())
            height = max(64, self._vp.winfo_height())
            self._pv_plotter.window_size = [width, height]
            image = self._pv_plotter.screenshot(return_img=True)
            if image is None or image.size == 0:
                return
            pil_image = Image.fromarray(image)
            self._pv_ctk_img = ctk.CTkImage(pil_image, size=(width, height))
            self._pv_label.configure(image=self._pv_ctk_img, text="")
        except Exception as exc:
            logger.debug("PyVista render failed: %s", exc)

    def _on_canvas_press(self, event) -> None:
        self._pv_drag = (event.x, event.y)

    def _on_canvas_drag(self, event) -> None:
        if self._pv_plotter is None or self._pv_drag is None:
            return
        dx = event.x - self._pv_drag[0]
        dy = event.y - self._pv_drag[1]
        self._pv_drag = (event.x, event.y)
        self._pv_plotter.camera.azimuth -= dx * 0.5
        self._pv_plotter.camera.elevation += dy * 0.5
        self._render_pv()

    def _on_canvas_scroll(self, event) -> None:
        if self._pv_plotter is None:
            return
        self._pv_plotter.camera.zoom(1.1 if event.delta > 0 else 0.9)
        self._render_pv()

    def _reset_camera(self) -> None:
        if self._pv_plotter is None:
            return
        self._pv_plotter.reset_camera()
        self._render_pv()

    def _set_camera_view(self, view: str) -> None:
        if self._pv_plotter is None:
            return
        try:
            if view == "xy":
                self._pv_plotter.view_xy()
            elif view == "xz":
                self._pv_plotter.view_xz()
            elif view == "yz":
                self._pv_plotter.view_yz()
            self._render_pv()
        except Exception as exc:
            logger.debug("Camera view failed: %s", exc)

    # ---------- Layers / colors ----------

    def _refresh_layers(self) -> None:
        for widget in self._layer_list.winfo_children():
            widget.destroy()
        for layer in self.scene.layers:
            row = ctk.CTkFrame(self._layer_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=1)
            prefix = {LayerType.POINT_CLOUD: "P", LayerType.MESH: "M", LayerType.DEM: "D"}.get(
                layer.layer_type, "L"
            )
            ctk.CTkLabel(
                row,
                text=f"{prefix} {layer.name}",
                font=FONT_SMALL,
                text_color=THEME["text_primary"],
                anchor="w",
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                row,
                text="显" if layer.visible else "隐",
                width=28,
                height=20,
                font=FONT_SMALL,
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=lambda lid=layer.id: self._toggle_layer(lid),
            ).pack(side="right", padx=1)
            ctk.CTkButton(
                row,
                text="X",
                width=20,
                height=20,
                font=("Segoe UI", 9),
                fg_color="transparent",
                text_color=THEME["danger"],
                hover_color=THEME["hover"],
                command=lambda lid=layer.id: self._remove_layer(lid),
            ).pack(side="right", padx=1)

    def _toggle_layer(self, layer_id: str) -> None:
        layer = self.scene.get_layer(layer_id)
        if layer is None:
            return
        layer.visible = not layer.visible
        self._render_layer(layer)
        self._refresh_layers()

    def _remove_layer(self, layer_id: str) -> None:
        layer = self.scene.get_layer(layer_id)
        if layer is None:
            return
        if self._pv_plotter is not None:
            try:
                self._pv_plotter.remove_actor(layer.id, reset_camera=False)
            except Exception:
                pass
        self.lod_mgr.remove_layer(layer.id)
        self.scene.remove_layer(layer_id)
        self._refresh_layers()
        self._refresh_point_count()
        self._render_pv()

    def _on_color_mode(self, mode: str) -> None:
        try:
            color_mode = ColorMode(mode)
        except ValueError:
            return
        for layer in self.scene.get_visible_layers():
            layer.color_mode = color_mode
            self._render_layer(layer)

    def _compute_colors(self, layer: SceneLayer, points: np.ndarray) -> np.ndarray | None:
        n = len(points)
        if layer.color_mode == ColorMode.RGB:
            try:
                if layer.geometry.has_colors():
                    colors = np.asarray(layer.geometry.colors, dtype=np.float64)
                    if len(colors) == n:
                        return colors[:, :3]
            except Exception:
                return None
        if layer.color_mode == ColorMode.ELEVATION:
            return apply_colormap(points[:, 2], layer.colormap).astype(np.float64)
        if layer.color_mode == ColorMode.CLASSIFICATION:
            classes = layer.attributes.get("classification")
            if classes is not None and len(classes) == n:
                return build_classification_colors(classes).astype(np.float64)
        if layer.color_mode == ColorMode.INTENSITY:
            intensity = layer.attributes.get("intensity")
            if intensity is not None and len(intensity) == n:
                return apply_colormap(intensity, "plasma").astype(np.float64)
        if layer.color_mode == ColorMode.NORMAL:
            try:
                normals = np.asarray(layer.geometry.normals, dtype=np.float64)
                if len(normals) == n:
                    return np.clip((normals + 1.0) / 2.0, 0, 1)
            except Exception:
                return None
        return None

    def _render_indices(self, count: int) -> np.ndarray:
        budget = max(1, int(getattr(self, "_render_budget", _MAX_RENDER_POINTS)))
        if count <= budget:
            return np.arange(count, dtype=np.int64)
        return np.linspace(0, count - 1, budget, dtype=np.int64)

    # ---------- Operations ----------

    def _get_active_point_layer(self) -> SceneLayer | None:
        for layer in self.scene.get_visible_layers():
            if layer.layer_type in (LayerType.POINT_CLOUD, LayerType.DEM):
                return layer
        return None

    def _layer_to_data(self, layer: SceneLayer) -> PointCloudData:
        points = np.asarray(layer.geometry.points, dtype=np.float64)
        colors = self._geometry_colors(layer)
        classes = layer.attributes.get("classification")
        if classes is not None and len(classes) != len(points):
            classes = None
        intensities = layer.attributes.get("intensity")
        if intensities is not None and len(intensities) != len(points):
            intensities = None
        normals = None
        try:
            if layer.geometry.has_normals():
                candidate = np.asarray(layer.geometry.normals, dtype=np.float64)
                if len(candidate) == len(points):
                    normals = candidate
        except Exception:
            normals = None
        return PointCloudData(
            points,
            colors=colors,
            classifications=classes,
            intensities=intensities,
            normals=normals,
            metadata=dict(layer.metadata),
        )

    def _apply_pointcloud_data(
        self,
        layer: SceneLayer,
        data: PointCloudData,
        color_mode: ColorMode | None = None,
        status: str = "",
    ) -> None:
        layer.geometry = data.to_o3d()
        layer.point_count = len(data.points)
        layer.metadata.update(
            {key: value for key, value in data.metadata.items() if not str(key).startswith("_")}
        )
        if data.classifications is not None and len(data.classifications) == layer.point_count:
            layer.attributes["classification"] = data.classifications
        else:
            layer.attributes.pop("classification", None)
        if data.intensities is not None and len(data.intensities) == layer.point_count:
            layer.attributes["intensity"] = data.intensities
        else:
            layer.attributes.pop("intensity", None)
        self._drop_mismatched_attributes(layer)
        if color_mode is not None:
            layer.color_mode = color_mode
            self._cm_var.set(color_mode.value)
        if layer.point_count:
            self.lod_mgr.build(
                layer.id,
                data.points,
                colors=data.colors,
                classifications=data.classifications,
            )
        else:
            self.lod_mgr.remove_layer(layer.id)
        self._render_layer(layer, reset_camera=True)
        self._refresh_point_count()
        if status:
            self._set_progress(1.0, status)

    def _create_processed_layer(
        self,
        source: SceneLayer,
        data: PointCloudData,
        name_suffix: str,
        color_mode: ColorMode | None = None,
    ) -> SceneLayer:
        layer = SceneLayer(
            name=self._unique_layer_name(f"{source.name}-{name_suffix}"),
            layer_type=source.layer_type,
            visible=True,
            opacity=source.opacity,
            source_path=source.source_path,
            crs=source.crs,
            epsg=source.epsg,
            point_size=source.point_size,
            color_mode=color_mode or source.color_mode,
            colormap=source.colormap,
            single_color=source.single_color,
            metadata=dict(source.metadata),
        )
        self.scene.add_layer(layer)
        self._apply_pointcloud_data(layer, data, color_mode=color_mode)
        return layer

    def _unique_layer_name(self, base_name: str) -> str:
        names = {layer.name for layer in self.scene.layers}
        if base_name not in names:
            return base_name
        index = 2
        while f"{base_name} {index}" in names:
            index += 1
        return f"{base_name} {index}"

    def _run_point_task(
        self,
        name: str,
        layer: SceneLayer,
        worker: Callable[..., PointCloudData],
        *,
        params: dict | None = None,
        backend: str = "cpu",
        output_mode: str = "replace",
        color_mode: ColorMode | None = None,
        after_apply: Callable[[SceneLayer, PointCloudData], str | None] | None = None,
    ) -> None:
        if self._task is not None and self._task.running:
            self._set_progress(0.0, "已有3D任务正在运行")
            return
        source = self._layer_to_data(layer).copy()
        layer_id = layer.id
        before_count = len(source.points)
        params = params or {}
        output_mode = "new" if output_mode == "new" else "replace"

        def _worker(
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            progress(0.08, f"{name}: 准备输入数据", "prepare")
            if cancel_event.is_set():
                return source
            progress(0.18, f"{name}: 后端 {self._backend_label(backend)}", "backend")
            progress(0.28, f"{name}: 正在计算", "compute")
            result = worker(source, cancel_event, progress)
            progress(0.86, f"{name}: 整理结果", "finalize")
            return result

        def _done(result: Viewer3DTaskResult[PointCloudData]) -> None:
            self.after(
                0,
                self._on_point_task_done,
                layer_id,
                before_count,
                result,
                params,
                backend,
                output_mode,
                color_mode,
                after_apply,
            )

        def _progress(event: Viewer3DTaskProgress) -> None:
            self.after(0, self._on_task_progress, event)

        self._task = Viewer3DTask(name, _worker, _done, _progress)
        self._set_progress(0.05, f"{name}处理中...")
        self._task.start()

    def _on_task_progress(self, event: Viewer3DTaskProgress) -> None:
        self._set_progress(event.value, event.text or f"{event.name}处理中...")

    def _on_point_task_done(
        self,
        layer_id: str,
        before_count: int,
        result: Viewer3DTaskResult[PointCloudData],
        params: dict,
        requested_backend: str,
        output_mode: str,
        color_mode: ColorMode | None,
        after_apply: Callable[[SceneLayer, PointCloudData], str | None] | None,
    ) -> None:
        self._task = None
        layer = self.scene.get_layer(layer_id)
        if layer is None:
            return
        if result.cancelled:
            self._set_progress(0.0, f"{result.name}已取消")
            return
        if result.error is not None:
            logger.error("%s failed: %s", result.name, result.error, exc_info=result.error)
            messagebox.showerror(f"{result.name}失败", str(result.error))
            return
        if result.value is None:
            return
        if output_mode == "new":
            target = self._create_processed_layer(layer, result.value, result.name, color_mode)
        else:
            target = layer
            self._apply_pointcloud_data(target, result.value, color_mode=color_mode)
        extra_status = after_apply(target, result.value) if after_apply is not None else ""
        self._refresh_layers()
        self._refresh_point_count()
        backend = str(result.value.metadata.get("compute_backend", requested_backend or "cpu"))
        output_label = "新图层" if output_mode == "new" else "覆盖当前"
        status = (
            f"{result.name}完成: {before_count:,} -> {len(result.value.points):,} 点，"
            f"{self._backend_label(backend)}，{output_label}"
        )
        if extra_status:
            status = f"{status}，{extra_status}"
        self._set_progress(1.0, status)
        self._push_history(
            result.name,
            before_count,
            len(result.value.points),
            result.elapsed_ms,
            backend,
            params=params,
            output=output_label,
            status="完成",
        )
        self._show_result_summary(
            result.name,
            before_count,
            len(result.value.points),
            result.elapsed_ms,
            backend,
            params,
            output_label,
            extra_status or "",
        )

    def _cancel_task(self) -> None:
        if self._task is not None and self._task.running:
            self._task.cancel()
            self._set_progress(0.0, f"正在取消{self._task.name}...")
        else:
            self._set_progress(0.0, "没有正在运行的3D任务")

    def _voxel(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "体素下采样",
            [
                {
                    "key": "voxel_size",
                    "label": "体素大小",
                    "var": self._voxel_var,
                    "unit": "m",
                    "min": 1e-9,
                }
            ],
            include_backend=True,
        )
        if not config:
            return
        backend = self._resolve_backend(config["backend_choice"])
        if backend is None:
            return
        voxel_size = float(config["params"]["voxel_size"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            progress(0.36, "体素下采样: 聚合体素网格", "compute")
            return (
                data
                if cancel_event.is_set()
                else voxel_downsample_data(data, voxel_size=voxel_size, use_gpu=backend)
            )

        self._run_point_task(
            "体素下采样",
            layer,
            _worker,
            params={"体素大小": f"{voxel_size:g} m"},
            backend=backend,
            output_mode=config["output_mode"],
        )

    def _sorf(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "统计去噪",
            [
                {
                    "key": "nb_neighbors",
                    "label": "邻域点数",
                    "var": self._sor_neighbors_var,
                    "type": "int",
                    "min": 3,
                },
                {"key": "std_ratio", "label": "标准差阈值", "var": self._sor_std_var, "min": 0.01},
            ],
        )
        if not config:
            return
        nb_neighbors = int(config["params"]["nb_neighbors"])
        std_ratio = float(config["params"]["std_ratio"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            progress(0.36, "统计去噪: 计算邻域距离", "compute")
            inliers, outliers = statistical_outlier_removal_data(
                data, nb_neighbors=nb_neighbors, std_ratio=std_ratio
            )
            inliers.metadata["removed_outliers"] = len(outliers.points)
            return inliers

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            removed = int(data.metadata.get("removed_outliers", 0))
            return f"移除 {removed:,} 点"

        self._run_point_task(
            "统计去噪",
            layer,
            _worker,
            params={"邻域点数": nb_neighbors, "标准差阈值": f"{std_ratio:g}"},
            output_mode=config["output_mode"],
            after_apply=_after,
        )

    def _radius_filter(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "半径去噪",
            [
                {
                    "key": "radius",
                    "label": "搜索半径",
                    "var": self._radius_var,
                    "unit": "m",
                    "min": 1e-9,
                },
                {
                    "key": "nb_points",
                    "label": "最少点数",
                    "var": self._radius_neighbors_var,
                    "type": "int",
                    "min": 1,
                },
            ],
        )
        if not config:
            return
        radius = float(config["params"]["radius"])
        nb_points = int(config["params"]["nb_points"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            progress(0.36, "半径去噪: 查询局部邻域", "compute")
            inliers, outliers = radius_outlier_removal_data(
                data, nb_points=nb_points, radius=radius
            )
            inliers.metadata["removed_outliers"] = len(outliers.points)
            return inliers

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            removed = int(data.metadata.get("removed_outliers", 0))
            return f"移除 {removed:,} 点"

        self._run_point_task(
            "半径去噪",
            layer,
            _worker,
            params={"搜索半径": f"{radius:g} m", "最少点数": nb_points},
            output_mode=config["output_mode"],
            after_apply=_after,
        )

    def _csf(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "地面分类",
            [
                {
                    "key": "cell_size",
                    "label": "格网大小",
                    "var": self._ground_cell_var,
                    "unit": "m",
                    "min": 1e-9,
                },
                {
                    "key": "height_threshold",
                    "label": "高度阈值",
                    "var": self._ground_height_var,
                    "unit": "m",
                    "min": 0.0,
                },
            ],
        )
        if not config:
            return
        cell_size = float(config["params"]["cell_size"])
        height_threshold = float(config["params"]["height_threshold"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            progress(0.36, "地面分类: 构建地形格网", "compute")
            ground, non_ground = smrf_filter_data(
                data, cell_size=cell_size, height_threshold=height_threshold
            )
            classified = classify_ground(data, ground, non_ground)
            classified.metadata["ground_count"] = len(ground.points)
            classified.metadata["non_ground_count"] = len(non_ground.points)
            return classified

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            ground_count = int(data.metadata.get("ground_count", 0))
            non_ground_count = int(data.metadata.get("non_ground_count", 0))
            return f"地面 {ground_count:,}，非地面 {non_ground_count:,}"

        self._run_point_task(
            "地面分类",
            layer,
            _worker,
            params={"格网大小": f"{cell_size:g} m", "高度阈值": f"{height_threshold:g} m"},
            output_mode=config["output_mode"],
            color_mode=ColorMode.CLASSIFICATION,
            after_apply=_after,
        )

    def _normalize_height(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "高度归一",
            [
                {
                    "key": "cell_size",
                    "label": "地面格网",
                    "var": self._ground_cell_var,
                    "unit": "m",
                    "min": 1e-9,
                },
                {
                    "key": "height_threshold",
                    "label": "地面阈值",
                    "var": self._ground_height_var,
                    "unit": "m",
                    "min": 0.0,
                },
            ],
        )
        if not config:
            return
        cell_size = float(config["params"]["cell_size"])
        height_threshold = float(config["params"]["height_threshold"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            if data.classifications is not None and np.any(data.classifications == 2):
                progress(0.36, "高度归一: 使用已有地面分类", "compute")
                ground = data.subset(np.nonzero(data.classifications == 2)[0])
            else:
                progress(0.36, "高度归一: 自动提取地面点", "compute")
                ground, _ = smrf_filter_data(
                    data, cell_size=cell_size, height_threshold=height_threshold
                )
            progress(0.64, "高度归一: 插值地面高度", "compute")
            return normalize_height(data, ground, cell_size=cell_size)

        self._run_point_task(
            "高度归一",
            layer,
            _worker,
            params={"地面格网": f"{cell_size:g} m", "地面阈值": f"{height_threshold:g} m"},
            output_mode=config["output_mode"],
        )

    def _estimate_normals(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "估计法线",
            [
                {
                    "key": "radius",
                    "label": "搜索半径",
                    "var": self._normal_radius_var,
                    "unit": "m",
                    "min": 0.0,
                },
                {
                    "key": "max_nn",
                    "label": "最大邻域",
                    "var": self._normal_nn_var,
                    "type": "int",
                    "min": 3,
                },
            ],
        )
        if not config:
            return
        radius = float(config["params"]["radius"])
        max_nn = int(config["params"]["max_nn"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            progress(0.36, "估计法线: 搜索邻域并拟合法向", "compute")
            return (
                data
                if cancel_event.is_set()
                else estimate_normals_data(data, radius=radius, max_nn=max_nn)
            )

        self._run_point_task(
            "估计法线",
            layer,
            _worker,
            params={"搜索半径": f"{radius:g} m", "最大邻域": max_nn},
            output_mode=config["output_mode"],
            color_mode=ColorMode.NORMAL,
        )

    def _roughness_curvature(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "粗糙/曲率",
            [
                {
                    "key": "k",
                    "label": "邻域点数",
                    "var": self._roughness_k_var,
                    "type": "int",
                    "min": 3,
                }
            ],
        )
        if not config:
            return
        k = int(config["params"]["k"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            progress(0.36, "粗糙/曲率: 计算局部邻域特征", "compute")
            roughness, curvature = local_roughness_curvature(data.points, k=k)
            out = data.copy()
            out.metadata["roughness_mean"] = float(np.mean(roughness)) if len(roughness) else 0.0
            out.metadata["curvature_mean"] = float(np.mean(curvature)) if len(curvature) else 0.0
            out.metadata["_roughness"] = roughness
            out.metadata["_curvature"] = curvature
            return out

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            roughness = data.metadata.get("_roughness")
            curvature = data.metadata.get("_curvature")
            if roughness is not None:
                target.attributes["roughness"] = roughness
            if curvature is not None:
                target.attributes["curvature"] = curvature
            return (
                f"rough={data.metadata.get('roughness_mean', 0.0):.3f}, "
                f"curv={data.metadata.get('curvature_mean', 0.0):.3f}"
            )

        self._run_point_task(
            "粗糙/曲率",
            layer,
            _worker,
            params={"邻域点数": k},
            output_mode=config["output_mode"],
            after_apply=_after,
        )

    def _crop_to_bbox_center(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "裁剪包围盒",
            [
                {
                    "key": "margin_percent",
                    "label": "边缘裁剪",
                    "default": "10",
                    "unit": "%",
                    "min": 0.0,
                    "max": 49.0,
                }
            ],
        )
        if not config:
            return
        margin_percent = float(config["params"]["margin_percent"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set() or len(data.points) == 0:
                return data
            progress(0.36, "裁剪包围盒: 计算空间范围", "compute")
            mins = data.points.min(axis=0)
            maxs = data.points.max(axis=0)
            margin = (maxs - mins) * (margin_percent / 100.0)
            inside, outside = crop_by_bounds_data(data, mins + margin, maxs - margin)
            inside.metadata["cropped_points"] = len(outside.points)
            return inside

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            removed = int(data.metadata.get("cropped_points", 0))
            return f"移除 {removed:,} 点"

        self._run_point_task(
            "裁剪包围盒",
            layer,
            _worker,
            params={"边缘裁剪": f"{margin_percent:g}%"},
            output_mode=config["output_mode"],
            after_apply=_after,
        )

    def _clip_z_median(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "Z 剖切",
            [
                {
                    "key": "height_mode",
                    "label": "高度模式",
                    "type": "choice",
                    "default": "Z中位",
                    "values": ["Z中位", "Z均值"],
                },
                {
                    "key": "keep_mode",
                    "label": "保留方向",
                    "type": "choice",
                    "default": "上半部",
                    "values": ["上半部", "下半部"],
                },
            ],
        )
        if not config:
            return
        height_mode = str(config["params"]["height_mode"])
        keep_mode = str(config["params"]["keep_mode"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set() or len(data.points) == 0:
                return data
            progress(0.36, "Z 剖切: 计算剖切平面", "compute")
            z_value = (
                float(np.mean(data.points[:, 2]))
                if height_mode == "Z均值"
                else float(np.median(data.points[:, 2]))
            )
            upper, lower = clip_by_plane_data(
                data, np.array([0.0, 0.0, z_value]), np.array([0.0, 0.0, 1.0])
            )
            kept, removed = (upper, lower) if keep_mode == "上半部" else (lower, upper)
            kept.metadata["clip_z"] = z_value
            kept.metadata["clipped_points"] = len(removed.points)
            return kept

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            return (
                f"Z={float(data.metadata.get('clip_z', 0.0)):.3f}，"
                f"移除 {int(data.metadata.get('clipped_points', 0)):,} 点"
            )

        self._run_point_task(
            "Z 剖切",
            layer,
            _worker,
            params={"高度模式": height_mode, "保留方向": keep_mode},
            output_mode=config["output_mode"],
            after_apply=_after,
        )

    def _generate_dem_dsm(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        config = self._show_algorithm_dialog(
            "生成DEM/DSM",
            [
                {
                    "key": "cell_size",
                    "label": "栅格大小",
                    "var": self._dem_cell_var,
                    "unit": "m",
                    "min": 1e-9,
                },
                {
                    "key": "grid_output",
                    "label": "栅格类型",
                    "type": "choice",
                    "default": "DEM/DSM/CHM",
                    "values": ["DEM/DSM/CHM", "DEM", "DSM", "CHM"],
                },
            ],
            include_backend=True,
        )
        if not config:
            return
        backend = self._resolve_backend(config["backend_choice"])
        if backend is None:
            return
        cell_size = float(config["params"]["cell_size"])
        grid_output = str(config["params"]["grid_output"])

        def _worker(
            data: PointCloudData,
            cancel_event: threading.Event,
            progress: Callable[[float, str, str], None],
        ) -> PointCloudData:
            if cancel_event.is_set():
                return data
            progress(0.36, "生成DEM/DSM: 栅格化点云", "compute")
            grids = pointcloud_to_grids(data, cell_size=cell_size, use_gpu=backend)
            out = data.copy()
            out.metadata["_grids"] = grids
            out.metadata["compute_backend"] = str(grids.get("compute_backend", "cpu"))
            return out

        def _after(target: SceneLayer, data: PointCloudData) -> str:
            grids = data.metadata.get("_grids")
            if not grids:
                return ""
            target.attributes["dem_grid"] = grids["dem"]
            target.attributes["dsm_grid"] = grids["dsm"]
            target.attributes["chm_grid"] = grids["chm"]
            target.metadata["grid_origin"] = grids["origin"].tolist()
            target.metadata["grid_cell_size"] = float(grids["cell_size"])
            target.metadata["grid_shape"] = list(grids["dem"].shape)
            target.metadata["compute_backend"] = str(grids.get("compute_backend", "cpu"))
            if "gpu_backend" in grids:
                target.metadata["gpu_backend"] = str(grids["gpu_backend"])
            target.color_mode = ColorMode.ELEVATION
            self._cm_var.set("elevation")
            self._render_layer(target)
            rows, cols = grids["dem"].shape
            return f"{rows} x {cols} 栅格，{grid_output}"

        self._run_point_task(
            "生成DEM/DSM",
            layer,
            _worker,
            params={"栅格大小": f"{cell_size:g} m", "栅格类型": grid_output},
            backend=backend,
            output_mode=config["output_mode"],
            color_mode=ColorMode.ELEVATION,
            after_apply=_after,
        )

    def _pick_center_point(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            return
        data = self._layer_to_data(layer)
        if len(data.points) == 0:
            return
        query = data.points.mean(axis=0)
        idx, dist = nearest_point(data.points, query)
        if idx < 0:
            return
        point = data.points[idx]
        layer.metadata["last_pick_index"] = int(idx)
        layer.metadata["last_pick_point"] = point.tolist()
        self._set_progress(
            1.0,
            f"点拾取: #{idx} ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f}), d={dist:.3f}",
        )

    def _drop_mismatched_attributes(self, layer: SceneLayer) -> None:
        n = layer.point_count
        for key in list(layer.attributes):
            if key.endswith("_grid"):
                continue
            try:
                if len(layer.attributes[key]) != n:
                    layer.attributes.pop(key, None)
            except Exception:
                layer.attributes.pop(key, None)

    # ---------- Export ----------

    def _export_las(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None or not layer.has_geometry:
            return
        if layer.metadata.get("sampled"):
            ok = messagebox.askyesno(
                "导出确认",
                "当前图层是为交互预览抽样加载的数据，导出将只包含已加载点。是否继续？",
            )
            if not ok:
                return
        path = filedialog.asksaveasfilename(
            title="导出 LAS",
            defaultextension=".las",
            filetypes=[("LAS", "*.las"), ("LAZ", "*.laz")],
        )
        if not path:
            return
        points = np.asarray(layer.geometry.points, dtype=np.float64)
        classes = layer.attributes.get("classification")
        colors = self._geometry_colors(layer)
        ok = export_las(points, path, classifications=classes, colors=colors, crs_wkt=layer.crs)
        self._set_progress(1.0, f"已导出 LAS: {Path(path).name}" if ok else "LAS 导出失败")

    def _export_ply(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None or not layer.has_geometry:
            return
        path = filedialog.asksaveasfilename(
            title="导出 PLY", defaultextension=".ply", filetypes=[("PLY", "*.ply")]
        )
        if not path:
            return
        points = np.asarray(layer.geometry.points, dtype=np.float64)
        colors = self._geometry_colors(layer)
        ok = export_ply(points, path, colors=colors)
        self._set_progress(1.0, f"已导出 PLY: {Path(path).name}" if ok else "PLY 导出失败")

    def _export_shot(self) -> None:
        if self._pv_plotter is None:
            return
        path = filedialog.asksaveasfilename(
            title="导出截图",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return
        try:
            self._pv_plotter.screenshot(path)
            self._set_progress(1.0, f"截图已保存: {Path(path).name}")
        except Exception as exc:
            logger.error("Screenshot export failed: %s", exc, exc_info=True)
            messagebox.showerror("截图导出失败", str(exc))

    def _geometry_colors(self, layer: SceneLayer) -> np.ndarray | None:
        try:
            if layer.geometry.has_colors():
                colors = np.asarray(layer.geometry.colors, dtype=np.float64)
                if len(colors) == layer.point_count:
                    return colors
        except Exception:
            return None
        return None

    # ---------- State / lifecycle ----------

    def _clear_all(self) -> None:
        if self._pv_plotter is not None:
            self._pv_plotter.clear()
            self._pv_plotter.set_background("#1a1a26")
            self._pv_plotter.show_axes()
        self.scene.clear()
        self.lod_mgr.clear()
        self._history.clear()
        self._refresh_layers()
        self._refresh_history()
        self._refresh_point_count()
        self._render_pv()
        self._set_progress(0.0, "已清除所有图层")

    def get_state(self) -> dict:
        return {"scene": self.scene.to_dict()}

    def set_state(self, state: dict) -> None:
        if state and "scene" in state:
            self.scene = SceneGraph.from_dict(state["scene"])
            self._pending_restore_layers = list(state["scene"].get("layers", []))
            self._restore_clear_pending = bool(self._pending_restore_layers)
            self._refresh_layers()
            if self.winfo_ismapped():
                self.after(50, self._restore_pending_layers)

    def destroy(self) -> None:
        if self._pv_plotter is not None:
            try:
                self._pv_plotter.close()
            except Exception:
                pass
        super().destroy()

    # ---------- Small helpers ----------

    def _float_var(self, var: ctk.StringVar, default: float, minimum: float | None = None) -> float:
        try:
            value = float(var.get())
        except (TypeError, ValueError):
            value = default
            var.set(str(default))
        if minimum is not None and value < minimum:
            value = minimum
            var.set(str(minimum))
        return value

    def _int_var(self, var: ctk.StringVar, default: int, minimum: int | None = None) -> int:
        try:
            value = int(float(var.get()))
        except (TypeError, ValueError):
            value = default
            var.set(str(default))
        if minimum is not None and value < minimum:
            value = minimum
            var.set(str(minimum))
        return value

    def _use_gpu(self) -> bool:
        return bool(self._gpu_var.get())

    def _set_quality(self, value: str) -> None:
        self._render_budget = int(_QUALITY_BUDGETS.get(value, _MAX_RENDER_POINTS))
        self.lod_mgr.set_render_budget(self._render_budget)
        self._set_progress(0.0, f"渲染质量: {value}，预算 {self._render_budget:,} 点")
        for layer in self.scene.get_visible_layers():
            self._render_layer(layer)

    def _redetect_gpu(self) -> None:
        clear_gpu_status_cache()
        self._refresh_gpu_status()
        status = get_gpu_status("auto")
        self._set_progress(1.0 if status.available else 0.0, f"GPU复检: {status.label}")

    def _show_gpu_setup(self) -> None:
        clear_gpu_status_cache()
        plan = get_gpu_setup_plan()
        message = format_gpu_setup_plan(plan)
        if plan.status.available:
            self._gpu_var.set(True)
            self._refresh_gpu_status()
            messagebox.showinfo("GPU加速可用", message)
            return
        if not plan.can_install:
            messagebox.showwarning("GPU修复建议", message)
            return
        ok = messagebox.askyesno("GPU修复", f"{message}\n\n是否现在自动安装推荐组件？")
        if ok:
            self._install_gpu_backend(plan.pip_args)

    def _install_gpu_backend(self, pip_args: tuple[str, ...]) -> None:
        if not pip_args:
            messagebox.showwarning("GPU修复", "没有可执行的安装命令。")
            return
        if self._task is not None and self._task.running:
            self._set_progress(0.0, "已有3D任务正在运行，请稍后再修复GPU")
            return

        def _worker(cancel_event: threading.Event, progress):
            progress(0.08, "GPU修复: 准备安装组件", "prepare")
            if cancel_event.is_set():
                return {"returncode": 1, "output": "用户已取消"}
            progress(0.18, "GPU修复: 正在安装 CuPy/CUDA 后端", "install")
            proc = subprocess.run(
                list(pip_args),
                capture_output=True,
                text=True,
                check=False,
            )
            output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
            progress(0.86, "GPU修复: 安装完成，正在复检", "verify")
            clear_gpu_status_cache()
            status = get_gpu_status("auto")
            return {"returncode": proc.returncode, "output": output, "status": status}

        def _done(result: Viewer3DTaskResult[dict]) -> None:
            self.after(0, self._on_gpu_install_done, result)

        def _progress(event: Viewer3DTaskProgress) -> None:
            self.after(0, self._on_task_progress, event)

        self._task = Viewer3DTask("GPU修复", _worker, _done, _progress)
        self._set_progress(0.05, "GPU修复: 开始安装")
        self._task.start()

    def _on_gpu_install_done(self, result: Viewer3DTaskResult[dict]) -> None:
        self._task = None
        if result.cancelled:
            self._set_progress(0.0, "GPU修复已取消")
            return
        if result.error is not None:
            logger.error("GPU setup failed: %s", result.error, exc_info=result.error)
            messagebox.showerror("GPU修复失败", str(result.error))
            return
        payload = result.value or {}
        status = payload.get("status") or get_gpu_status("auto")
        self._gpu_var.set(bool(status.available))
        self._refresh_gpu_status()
        if status.available:
            self._set_progress(1.0, f"GPU修复完成: {status.label}")
            messagebox.showinfo("GPU修复完成", f"GPU加速已启用：{status.label}")
            return
        output = str(payload.get("output", "")).strip()
        returncode = payload.get("returncode", "")
        self._set_progress(0.0, "GPU修复未完成，已保留CPU后端")
        messagebox.showwarning(
            "GPU修复未完成",
            (
                f"安装命令返回码：{returncode}\n"
                f"复检结果：{status.label}\n\n"
                f"{output[-1600:] if output else '没有安装输出。'}"
            ),
        )

    def _refresh_gpu_status(self, prompt: bool = False) -> None:
        try:
            status = get_gpu_status("auto")
            prefix = "GPU开启" if self._gpu_var.get() else "GPU关闭"
            detail = status.label if status.available else status.reason
            self._gpu_status_lbl.configure(text=f"{prefix}: {detail}")
            if prompt:
                if self._gpu_var.get() and status.available:
                    messagebox.showinfo("GPU加速", f"GPU加速已启用：{status.label}")
                elif self._gpu_var.get():
                    self._gpu_var.set(False)
                    self._gpu_status_lbl.configure(text=f"GPU关闭: {detail}")
                    ok = messagebox.askyesno(
                        "GPU不可用",
                        (
                            f"GPU加速未启用，将使用CPU计算。\n原因：{detail}\n\n"
                            "是否打开检测/修复向导？"
                        ),
                    )
                    if ok:
                        self._show_gpu_setup()
                else:
                    self._set_progress(0.0, "GPU加速已关闭，后续计算默认使用CPU/自动后端")
        except Exception as exc:
            self._gpu_status_lbl.configure(text=f"GPU状态未知: {exc}")
            if prompt:
                messagebox.showwarning("GPU状态未知", str(exc))

    def _resolve_backend(self, choice: str) -> str | None:
        choice = (choice or "CPU").strip()
        if choice == "CPU":
            return "cpu"
        if choice == "自动":
            status = get_gpu_status("auto")
            return "auto" if status.available else "cpu"
        status = get_gpu_status("cupy")
        if status.available:
            return "cupy"
        ok = messagebox.askyesno(
            "GPU不可用",
            f"当前GPU后端不可用，原因：{status.reason or status.label}\n是否改用CPU继续？",
        )
        if ok:
            return "cpu"
        self._set_progress(0.0, "已取消：GPU不可用")
        return None

    @staticmethod
    def _backend_label(backend: str) -> str:
        value = (backend or "cpu").lower()
        if value == "cupy":
            return "GPU(CuPy)"
        if value == "auto":
            return "自动(GPU优先)"
        return "CPU"

    def _push_history(
        self,
        name: str,
        before: int,
        after: int,
        elapsed_ms: float,
        backend: str = "cpu",
        *,
        params: dict | None = None,
        output: str = "",
        status: str = "完成",
    ) -> None:
        removed = max(0, before - after)
        pct = (removed / before * 100.0) if before else 0.0
        param_text = self._format_params(params or {})
        detail_parts = [f"移除 {removed:,} ({pct:.1f}%)" if removed else "点数未减少"]
        if output:
            detail_parts.append(output)
        if param_text:
            detail_parts.append(param_text)
        self._history.insert(
            0,
            {
                "name": f"{status} · {name}",
                "summary": (
                    f"{before:,} -> {after:,} 点，{elapsed_ms:.0f} ms，"
                    f"{self._backend_label(backend)}"
                ),
                "detail": " | ".join(detail_parts),
            },
        )
        del self._history[12:]
        self._refresh_history()

    def _show_result_summary(
        self,
        name: str,
        before: int,
        after: int,
        elapsed_ms: float,
        backend: str,
        params: dict,
        output: str,
        extra: str = "",
    ) -> None:
        lines = [
            f"任务：{name}",
            f"点数：{before:,} -> {after:,}",
            f"耗时：{elapsed_ms:.0f} ms",
            f"后端：{self._backend_label(backend)}",
            f"输出：{output}",
        ]
        param_text = self._format_params(params)
        if param_text:
            lines.append(f"参数：{param_text}")
        if extra:
            lines.append(f"结果：{extra}")
        try:
            messagebox.showinfo(f"{name}完成", "\n".join(lines))
        except Exception:
            pass

    @staticmethod
    def _format_params(params: dict | None) -> str:
        if not params:
            return ""
        return "，".join(f"{key}={value}" for key, value in params.items())

    def _refresh_history(self) -> None:
        history_list = getattr(self, "_history_list", None)
        if history_list is None:
            return
        for widget in history_list.winfo_children():
            widget.destroy()
        if not self._history:
            ctk.CTkLabel(
                history_list,
                text="暂无任务",
                font=FONT_SMALL,
                text_color=THEME["text_muted"],
            ).pack(anchor="w", padx=2, pady=4)
            return
        for item in self._history:
            row = ctk.CTkFrame(history_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(
                row,
                text=item["name"],
                font=FONT_SMALL,
                text_color=THEME["text_primary"],
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                row,
                text=f"{item['summary']} | {item['detail']}",
                font=FONT_SMALL,
                text_color=THEME["text_secondary"],
                anchor="w",
            ).pack(anchor="w")

    def _refresh_point_count(self) -> None:
        layer = self._get_active_point_layer()
        if layer is None:
            self._pt_lbl.configure(text="")
            return
        source_count = layer.metadata.get("source_point_count") or layer.metadata.get(
            "source_cells"
        )
        if source_count and int(source_count) != layer.point_count:
            backend = layer.metadata.get("compute_backend", "cpu")
            self._pt_lbl.configure(
                text=f"当前: {layer.point_count:,} / 源 {int(source_count):,} | {backend}"
            )
        else:
            backend = layer.metadata.get("compute_backend", "cpu")
            self._pt_lbl.configure(text=f"当前: {layer.point_count:,} | {backend}")

    def _layer_status(self, layer: SceneLayer) -> str:
        source_count = layer.metadata.get("source_point_count") or layer.metadata.get(
            "source_cells"
        )
        if source_count and int(source_count) != layer.point_count:
            return f"已加载预览: {layer.name} {layer.point_count:,} / 源 {int(source_count):,}"
        if layer.layer_type == LayerType.MESH:
            return f"已加载: {layer.name} {layer.point_count:,} 顶点 / {layer.face_count:,} 面"
        return f"已加载: {layer.name} {layer.point_count:,}"

    def _set_progress(self, value: float, text: str) -> None:
        try:
            self._prog.set(max(0.0, min(1.0, float(value))))
            self._prog_lbl.configure(text=text)
        except Exception:
            pass
