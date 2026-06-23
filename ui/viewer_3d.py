"""3D Viewer widget — Open3D rendering embedded in a CustomTkinter Toplevel.

Provides a production-grade point cloud / mesh viewer with:
- Open3D native rendering via embedded HWND
- Layer management backed by SceneGraph
- LOD octree for large datasets
- Pan / zoom / rotate camera controls
- Classification / elevation / intensity color modes
- Point cloud processing pipeline (voxel, filter, ground, normals)
- LAS/PLY export with classification support
- Profile analysis with chart visualization
- Undo/redo for 3D operations
- Coordinate display in status bar

Usage:
    viewer = Viewer3DWindow(parent_window, "My 3D View")
    viewer.load_pointcloud("scan.las")
    viewer.load_mesh("model.obj")
"""

from __future__ import annotations

import ctypes
import math
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk
import numpy as np

from common.logger import logger

try:
    import open3d as o3d
    import open3d.visualization.gui as gui
    import open3d.visualization.rendering as rendering

    _O3D_GUI = True
except ImportError:
    _O3D_GUI = False
    logger.warning("open3d.visualization.gui not available; 3D viewer disabled")

from core.mesh_ops import load_mesh as o3d_load_mesh
from core.pointcloud_io import export_las, export_ply, export_xyz
from core.pointcloud_ops import (
    build_classification_colors,
    estimate_normals,
    to_o3d_pointcloud,
    voxel_downsample,
)
from core.resource_manager import read_scene_preview
from core.scene_graph import (
    ColorMode,
    LayerType,
    SceneGraph,
    SceneLayer,
    apply_colormap,
    get_classification_color,
)
from core.terrain_analysis import hillshade, slope

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, THEME
from .viewer_3d_lod import LODManager
from .viewer_3d_profile_dialog import ProfileDialog

_POINT_CHUNK_SIZE = 500_000
_MAX_POINTS_IN_MEMORY = 3_000_000


# ---- platform helpers ----


def _get_native_hwnd(o3d_window) -> Optional[int]:
    """Extract the native HWND from an Open3D gui.Window."""
    try:
        import win32con
        import win32gui

        title = o3d_window.title if hasattr(o3d_window, "title") else "Open3D"
        hwnd = win32gui.FindWindow(None, title)
        if hwnd:
            return hwnd
        hwnd = win32gui.GetForegroundWindow()
        return hwnd
    except Exception:
        return None


def _embed_hwnd(o3d_hwnd: int, tk_frame: ctk.CTkFrame) -> bool:
    """Reparent the Open3D native window into a tkinter Frame."""
    try:
        import win32con
        import win32gui

        tk_frame.update_idletasks()
        parent_hwnd = tk_frame.winfo_id()
        old_parent = win32gui.SetParent(o3d_hwnd, parent_hwnd)
        style = win32gui.GetWindowLong(o3d_hwnd, win32con.GWL_STYLE)
        style = (style & ~win32con.WS_CAPTION) | win32con.WS_CHILD
        win32gui.SetWindowLong(o3d_hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(
            o3d_hwnd,
            0,
            0,
            0,
            tk_frame.winfo_width(),
            tk_frame.winfo_height(),
            win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW,
        )
        return True
    except Exception as exc:
        logger.warning(f"HWND embed failed: {exc}")
        return False


# ---- Viewer3DWindow ----


class Viewer3DWindow(ctk.CTkToplevel):
    """Standalone 3D viewer toplevel with full Open3D rendering."""

    def __init__(
        self, parent, title: str = "RSTao 3D Viewer", width: int = 1200, height: int = 800
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(800, 500)
        self.configure(fg_color=THEME["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.scene = SceneGraph()
        self.lod_mgr = LODManager()
        self._o3d_window: Any = None
        self._o3d_scene: Any = None
        self._o3d_scene_widget: Any = None
        self._camera_params: dict[str, Any] = {}
        self._loading = False
        self._current_tool: Optional[str] = None
        self._o3d_ready = False
        self._pending_resources: list[dict[str, str]] = []

        self._build_ui()

    # ---------- UI construction ----------

    def _build_ui(self):
        # Top toolbar
        self._toolbar = ctk.CTkFrame(self, height=38, fg_color=THEME["statusbar"])
        self._toolbar.pack(fill="x", side="top")
        self._build_toolbar_buttons()

        # Main area: 3D viewport
        self._viewport = ctk.CTkFrame(self, fg_color="#1a1a1f")
        self._viewport.pack(fill="both", expand=True, side="top")

        # Status bar
        self._status = ctk.CTkFrame(self, height=26, fg_color=THEME["statusbar"])
        self._status.pack(fill="x", side="bottom")
        self._status_label = ctk.CTkLabel(
            self._status,
            text="就绪",
            font=("Consolas", 10),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self._status_label.pack(side="left", padx=10)
        self._coord_label = ctk.CTkLabel(
            self._status,
            text="",
            font=("Consolas", 10),
            text_color=THEME["text_secondary"],
            anchor="e",
        )
        self._coord_label.pack(side="right", padx=10)

        # Side layer panel
        self._layer_panel = ctk.CTkFrame(self, width=260, fg_color=THEME["panel"])
        self._layer_panel.pack(fill="y", side="right", padx=(0, 0), pady=(0, 0))
        self._layer_panel.pack_propagate(False)
        self._build_layer_panel()

        # Defer Open3D init until this toplevel is mapped
        self.after(100, self._init_open3d)

    def _build_toolbar_buttons(self):
        buttons = [
            ("导入点云", self._import_pointcloud),
            ("导入Mesh", self._import_mesh),
            ("导入DEM", self._import_dem),
            ("", None),
            ("自适应", self._fit_view),
            ("俯视", lambda: self._set_view("top")),
            ("正视", lambda: self._set_view("front")),
            ("侧视", lambda: self._set_view("side")),
            ("", None),
            ("清除", self._clear_all),
            ("导出截图", self._export_screenshot),
            ("", None),
            ("导出LAS", self._export_las),
            ("导出PLY", self._export_ply),
        ]
        for text, cmd in buttons:
            if not text:
                sep = ctk.CTkFrame(self._toolbar, width=1, height=20, fg_color=THEME["border"])
                sep.pack(side="left", padx=4, pady=8)
                continue
            btn = ctk.CTkButton(
                self._toolbar,
                text=text,
                width=70,
                height=28,
                font=("Microsoft YaHei UI", 11),
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=cmd,
            )
            btn.pack(side="left", padx=1, pady=4)

    def _build_layer_panel(self):
        header = ctk.CTkFrame(self._layer_panel, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            header, text="图层", font=FONT_SUBTITLE, text_color=THEME["text_primary"]
        ).pack(side="left")

        self._layer_list = ctk.CTkScrollableFrame(
            self._layer_panel, fg_color="transparent", height=300
        )
        self._layer_list.pack(fill="both", expand=True, padx=4, pady=4)

        # Color control card
        self._color_card = ctk.CTkFrame(self._layer_panel, fg_color=THEME["card"], corner_radius=6)
        self._color_card.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(
            self._color_card, text="着色模式", font=FONT_SMALL, text_color=THEME["text_secondary"]
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self._color_mode_var = ctk.StringVar(value="rgb")
        modes = [
            ("RGB", "rgb"),
            ("分类", "classification"),
            ("高程", "elevation"),
            ("强度", "intensity"),
            ("法线", "normal"),
        ]
        for label, mode in modes:
            rb = ctk.CTkRadioButton(
                self._color_card,
                text=label,
                variable=self._color_mode_var,
                value=mode,
                font=FONT_SMALL,
                command=lambda m=mode: self._on_color_mode_changed(m),
            )
            rb.pack(anchor="w", padx=10, pady=1)

        ctk.CTkLabel(
            self._color_card, text="点大小", font=FONT_SMALL, text_color=THEME["text_secondary"]
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self._point_size_slider = ctk.CTkSlider(
            self._color_card,
            from_=0.5,
            to=10,
            number_of_steps=19,
            command=self._on_point_size_changed,
        )
        self._point_size_slider.pack(fill="x", padx=10, pady=(0, 8))
        self._point_size_slider.set(2.0)

        # Processing card
        self._proc_card = ctk.CTkFrame(self._layer_panel, fg_color=THEME["card"], corner_radius=6)
        self._proc_card.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkLabel(
            self._proc_card, text="点云处理", font=FONT_SMALL, text_color=THEME["text_secondary"]
        ).pack(anchor="w", padx=10, pady=(8, 2))

        proc_buttons = [
            ("体素下采样", self._voxel_downsample),
            ("统计滤波去噪", self._statistical_filter),
            ("地面滤波", self._ground_filter),
            ("估计法线", self._estimate_normals),
            ("剖面分析...", self._open_profile_tool),
        ]
        for text, cmd in proc_buttons:
            ctk.CTkButton(
                self._proc_card,
                text=text,
                width=120,
                height=26,
                font=FONT_SMALL,
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=cmd,
            ).pack(anchor="w", padx=6, pady=1)

        pc_label = ctk.CTkLabel(
            self._proc_card, text="点云数: 一", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        pc_label.pack(anchor="w", padx=10, pady=(4, 8))

    # ---------- Open3D init ----------

    def _init_open3d(self):
        if not _O3D_GUI:
            self._status_label.configure(text="Open3D GUI 不可用")
            return
        try:
            gui.Application.instance.initialize()
            self._o3d_window = gui.Application.instance.create_window(
                "RSTao3D", self._viewport.winfo_width(), self._viewport.winfo_height()
            )
            self._o3d_scene = rendering.Open3DScene(self._o3d_window.renderer)
            self._o3d_scene_widget = gui.SceneWidget()
            self._o3d_scene_widget.scene = self._o3d_scene
            self._o3d_window.add_child(self._o3d_scene_widget)
            self._o3d_scene.set_background(np.array(self.scene.background_color, dtype=np.float32))
            self.after(200, self._try_embed)
        except Exception as exc:
            logger.error(f"Open3D init failed: {exc}")
            self._status_label.configure(text=f"Open3D 初始化失败: {exc}")

    def _try_embed(self):
        if self._o3d_window is None:
            return
        hwnd = _get_native_hwnd(self._o3d_window)
        if hwnd and _embed_hwnd(hwnd, self._viewport):
            self._status_label.configure(text="3D 视图就绪 — 导入点云或Mesh开始")
            self._o3d_ready = True
            self._drain_pending_resources()
            self._start_render_loop()
        else:
            self.after(200, self._try_embed)

    def _renderer_ready(self) -> bool:
        return (
            self._o3d_ready and self._o3d_scene is not None and self._o3d_scene_widget is not None
        )

    def _queue_resource(self, path: str, source_type: str) -> None:
        if not path:
            return
        self._pending_resources.append({"source_path": path, "source_type": source_type})
        self._status_label.configure(text="3D 视图初始化中，资源将在就绪后加载")

    def _drain_pending_resources(self) -> None:
        if not self._renderer_ready() or self._loading:
            return
        if self._pending_resources:
            self.load_from_resource(self._pending_resources.pop(0))

    def _start_render_loop(self):
        def _loop():
            while self.winfo_exists():
                try:
                    gui.Application.instance.run_one_tick()
                except Exception:
                    break

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ---------- Import ----------

    def _import_pointcloud(self):
        paths = filedialog.askopenfilenames(
            title="导入点云",
            filetypes=[
                ("点云文件", "*.las *.laz *.pcd *.ply *.xyz *.txt *.csv *.pts"),
                ("所有文件", "*.*"),
            ],
        )
        for path in paths:
            self._load_pointcloud(path)

    def _load_pointcloud(self, path: str):
        if not self._renderer_ready():
            self._queue_resource(path, "pointcloud")
            return
        if self._loading:
            return
        self._loading = True
        name = Path(path).name
        self._status_label.configure(text="Chunk loading: " + name + " 0%")
        self.update_idletasks()

        def _do():
            try:
                chunk_size = _POINT_CHUNK_SIZE
                pts_list = []
                clr_list = []
                cls_list = []
                total = self._estimate_point_count(path)
                sampled = False
                crs = ""

                if path.lower().endswith((".las", ".laz")):
                    import laspy

                    with laspy.open(path) as las_file:
                        total = int(las_file.header.point_count)
                        stride = max(1, math.ceil(total / _MAX_POINTS_IN_MEMORY))
                        sampled = stride > 1
                        try:
                            parsed_crs = las_file.header.parse_crs()
                            crs = parsed_crs.to_wkt() if parsed_crs else ""
                        except Exception:
                            crs = ""
                        for i, points_chunk in enumerate(las_file.chunk_iterator(chunk_size)):
                            x = np.asarray(points_chunk.x, dtype=np.float64)
                            y = np.asarray(points_chunk.y, dtype=np.float64)
                            z = np.asarray(points_chunk.z, dtype=np.float64)
                            pts = np.column_stack([x, y, z])
                            pts_list.append(pts[::stride] if stride > 1 else pts)
                            if hasattr(points_chunk, "red"):
                                r = np.asarray(points_chunk.red, dtype=np.float32) / 65535.0
                                g = np.asarray(points_chunk.green, dtype=np.float32) / 65535.0
                                b = np.asarray(points_chunk.blue, dtype=np.float32) / 65535.0
                                colors = np.column_stack([r, g, b])
                                clr_list.append(colors[::stride] if stride > 1 else colors)
                            if hasattr(points_chunk, "classification"):
                                cls = np.asarray(points_chunk.classification, dtype=np.int32)
                                cls_list.append(cls[::stride] if stride > 1 else cls)
                            pct = min(1.0, (i + 1) * chunk_size / max(total, 1))
                            msg = "Chunk loading: " + name + " " + str(int(pct * 100)) + "%"
                            self.after(0, lambda m=msg: self._status_label.configure(text=m))
                else:
                    preview = read_scene_preview(path, max_points=_MAX_POINTS_IN_MEMORY)
                    if preview.vertices.size > 0:
                        pts_list.append(preview.vertices.astype(np.float64))
                        if preview.colors is not None:
                            clr_list.append(np.asarray(preview.colors, dtype=np.float64))
                        total = len(preview.vertices)

                if not pts_list:
                    self.after(0, lambda: messagebox.showwarning("Load fail", "empty"))
                    return

                pts = np.vstack(pts_list)
                clr = np.vstack(clr_list) if clr_list else None
                cls_ids = np.concatenate(cls_list) if cls_list else None
                total_loaded = len(pts)

                pcd = to_o3d_pointcloud(pts, clr)

                layer = SceneLayer(
                    name=Path(path).stem,
                    layer_type=LayerType.POINT_CLOUD,
                    source_path=path,
                    geometry=pcd,
                    point_count=total_loaded,
                    crs=crs,
                    metadata={
                        "source_point_count": total,
                        "loaded_point_count": total_loaded,
                        "sampled": sampled,
                    },
                )
                if cls_ids is not None and len(cls_ids) == total_loaded:
                    layer.attributes["classification"] = cls_ids

                self.lod_mgr.build(layer.id, pts, colors=clr, classifications=cls_ids)
                self.after(0, self._add_point_layer_to_scene, layer, pcd, total_loaded)
            except Exception as exc:
                logger.error("Load fail: " + str(exc))
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _add_point_layer_to_scene(self, layer: SceneLayer, pcd, loaded_count: int):
        if not self._renderer_ready():
            self._pending_resources.insert(
                0, {"source_path": layer.source_path, "source_type": layer.layer_type.value}
            )
            return
        mat = rendering.MaterialRecord()
        mat.shader = "defaultUnlit"
        mat.point_size = float(self._point_size_slider.get())
        self.scene.add_layer(layer)
        self._o3d_scene.add_geometry(self._geom_name(layer), pcd, mat)
        self._on_load_done(layer, loaded_count)
        self.after(150, self._drain_pending_resources)

    def _estimate_point_count(self, path: str) -> int:
        try:
            if path.lower().endswith((".las", ".laz")):
                import laspy

                with laspy.open(path) as las:
                    return int(las.header.point_count)
            return 500_000
        except Exception:
            return 500_000

    def _import_mesh(self):
        paths = filedialog.askopenfilenames(
            title="导入Mesh",
            filetypes=[("Mesh文件", "*.obj *.ply *.stl *.glb *.gltf *.off"), ("所有文件", "*.*")],
        )
        for path in paths:
            self._load_mesh(path)

    def _load_mesh(self, path: str):
        if not self._renderer_ready():
            self._queue_resource(path, "mesh")
            return
        if self._loading:
            return
        self._loading = True
        self._status_label.configure(text=f"加载Mesh: {Path(path).name} ...")

        def _do():
            try:
                mesh = o3d_load_mesh(path)
                vertices = np.asarray(mesh.vertices)
                verts = len(vertices)
                faces = len(np.asarray(mesh.triangles))
                if faces:
                    geometry = mesh
                    layer_type = LayerType.MESH
                else:
                    geometry = to_o3d_pointcloud(vertices)
                    layer_type = LayerType.POINT_CLOUD

                layer = SceneLayer(
                    name=Path(path).stem,
                    layer_type=layer_type,
                    source_path=path,
                    geometry=geometry,
                    point_count=verts,
                    face_count=faces,
                )
                self.after(0, self._add_mesh_layer_to_scene, layer, geometry, verts, faces)
            except Exception as exc:
                logger.error(f"Mesh load failed: {exc}")
                self.after(0, lambda: messagebox.showerror("加载失败", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _add_mesh_layer_to_scene(self, layer: SceneLayer, geometry, verts: int, faces: int):
        if not self._renderer_ready():
            self._pending_resources.insert(
                0, {"source_path": layer.source_path, "source_type": "mesh"}
            )
            return
        mat = rendering.MaterialRecord()
        if layer.layer_type == LayerType.MESH:
            mat.shader = "defaultLit"
            mat.base_color = (0.6, 0.7, 0.85, 1.0)
        else:
            mat.shader = "defaultUnlit"
            mat.point_size = float(self._point_size_slider.get())
        self.scene.add_layer(layer)
        self._o3d_scene.add_geometry(self._geom_name(layer), geometry, mat)
        if layer.layer_type == LayerType.MESH:
            self._on_mesh_load_done(layer, verts, faces)
        else:
            self._on_load_done(layer, verts)
        self.after(150, self._drain_pending_resources)

    def _on_mesh_load_done(self, layer: SceneLayer, verts: int, faces: int):
        self._status_label.configure(text=f"已加载: {layer.name} — {verts:,} 顶点, {faces:,} 面")
        self._refresh_layer_list()
        self._fit_view()

    def _on_load_done(self, layer: SceneLayer, loaded_count: int):
        source_count = (
            layer.metadata.get("source_point_count")
            or layer.metadata.get("source_cells")
            or loaded_count
        )
        if source_count and int(source_count) != int(loaded_count):
            text = f"已加载预览: {layer.name} — {loaded_count:,} / 源 {int(source_count):,}"
        else:
            text = f"已加载: {layer.name} — {loaded_count:,} 点"
        self._status_label.configure(text=text)
        self._refresh_layer_list()
        self._refresh_point_count_display()
        self._fit_view()

    def _import_dem(self):
        paths = filedialog.askopenfilenames(
            title="导入DEM", filetypes=[("GeoTIFF", "*.tif *.tiff"), ("所有文件", "*.*")]
        )
        for path in paths:
            self._load_dem(path)

    def _load_dem(self, path: str):
        if not self._renderer_ready():
            self._queue_resource(path, "raster")
            return
        if self._loading:
            return
        self._loading = True
        self._status_label.configure(text=f"加载DEM: {Path(path).name} ...")

        def _do():
            try:
                import rasterio

                with rasterio.open(path) as ds:
                    dem = ds.read(1).astype(np.float32)
                    if ds.nodata is not None:
                        dem[dem == ds.nodata] = np.nan
                    transform = ds.transform
                    crs = ds.crs.to_wkt() if ds.crs else ""

                rows, cols = dem.shape
                max_cells = _MAX_POINTS_IN_MEMORY
                stride = max(1, math.ceil(math.sqrt((rows * cols) / max_cells)))
                dem_sample = dem[::stride, ::stride]
                valid_mean = float(np.nanmean(dem_sample)) if np.isfinite(dem_sample).any() else 0.0

                sample_rows = np.arange(0, rows, stride, dtype=np.float64)
                sample_cols = np.arange(0, cols, stride, dtype=np.float64)
                cc, rr = np.meshgrid(sample_cols + 0.5, sample_rows + 0.5)
                xx = transform.c + cc * transform.a + rr * transform.b
                yy = transform.f + cc * transform.d + rr * transform.e
                zz = np.nan_to_num(dem_sample, nan=valid_mean)

                pts = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
                cell_size = max(abs(float(transform.a)), abs(float(transform.e)), 1e-6) * stride
                hs = hillshade(np.nan_to_num(dem_sample, nan=valid_mean), cell_size=cell_size)
                colors = np.column_stack([hs.ravel()] * 3).astype(np.float64)

                pcd = to_o3d_pointcloud(pts, colors)
                layer = SceneLayer(
                    name=Path(path).stem,
                    layer_type=LayerType.DEM,
                    source_path=path,
                    geometry=pcd,
                    point_count=len(pts),
                    crs=crs,
                    color_mode=ColorMode.ELEVATION,
                    metadata={
                        "source_cells": rows * cols,
                        "loaded_cells": len(pts),
                        "sampled": stride > 1,
                        "dem_stride": stride,
                    },
                )

                self.after(0, self._add_dem_layer_to_scene, layer, pcd, len(pts))
            except Exception as exc:
                logger.error(f"DEM load failed: {exc}")
                self.after(0, lambda: messagebox.showerror("加载失败", str(exc)))
            finally:
                self.after(0, lambda: setattr(self, "_loading", False))

        threading.Thread(target=_do, daemon=True).start()

    def _add_dem_layer_to_scene(self, layer: SceneLayer, pcd, loaded_count: int):
        if not self._renderer_ready():
            self._pending_resources.insert(
                0, {"source_path": layer.source_path, "source_type": "raster"}
            )
            return
        mat = rendering.MaterialRecord()
        mat.shader = "defaultUnlit"
        mat.point_size = 2.0
        self.scene.add_layer(layer)
        self._o3d_scene.add_geometry(self._geom_name(layer), pcd, mat)
        self._on_load_done(layer, loaded_count)
        self.after(150, self._drain_pending_resources)

    # ---------- Layer list ----------

    def _refresh_layer_list(self):
        for w in self._layer_list.winfo_children():
            w.destroy()
        for layer in self.scene.layers:
            row = ctk.CTkFrame(self._layer_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=2)

            prefix = "■" if layer.layer_type == LayerType.POINT_CLOUD else "▲"
            label = f"{prefix} {layer.name}"
            vis_text = "👁" if layer.visible else "—"

            ctk.CTkLabel(
                row, text=label, font=FONT_SMALL, text_color=THEME["text_primary"], anchor="w"
            ).pack(side="left", padx=4)

            toggle = ctk.CTkButton(
                row,
                text=vis_text,
                width=28,
                height=22,
                font=("Segoe UI", 10),
                fg_color="transparent",
                text_color=THEME["text_primary"],
                hover_color=THEME["hover"],
                command=lambda lid=layer.id: self._toggle_layer(lid),
            )
            toggle.pack(side="right", padx=2)

            remove = ctk.CTkButton(
                row,
                text="✕",
                width=22,
                height=22,
                font=("Segoe UI", 10),
                fg_color="transparent",
                text_color=THEME["danger"],
                hover_color=THEME["hover"],
                command=lambda lid=layer.id: self._remove_layer(lid),
            )
            remove.pack(side="right", padx=1)

    def _toggle_layer(self, layer_id: str):
        layer = self.scene.get_layer(layer_id)
        if layer is None:
            return
        layer.visible = not layer.visible
        geom_name = self._geom_name(layer)
        if layer.visible:
            self._o3d_scene.show_geometry(geom_name, True)
        else:
            self._o3d_scene.show_geometry(geom_name, False)
        self._refresh_layer_list()

    def _remove_layer(self, layer_id: str):
        layer = self.scene.get_layer(layer_id)
        if layer is None:
            return
        self._o3d_scene.remove_geometry(self._geom_name(layer))
        self.lod_mgr.remove_layer(layer.id)
        self.scene.remove_layer(layer_id)
        self._refresh_layer_list()

    @staticmethod
    def _geom_name(layer: SceneLayer) -> str:
        prefix = {
            LayerType.POINT_CLOUD: "pc_",
            LayerType.MESH: "mesh_",
            LayerType.DEM: "dem_",
        }.get(layer.layer_type, "pc_")
        return f"{prefix}{layer.id}"

    # ---------- Color modes ----------

    def _on_color_mode_changed(self, mode: str):
        cm = ColorMode(mode)
        for layer in self.scene.get_visible_layers():
            layer.color_mode = cm
            self._apply_layer_colors(layer)

    def _apply_layer_colors(self, layer: SceneLayer):
        geom_name = self._geom_name(layer)
        try:
            geom = self._o3d_scene.get_geometry(geom_name)
            if geom is None:
                return
            pts = np.asarray(geom.points).astype(np.float64)
            if pts.size == 0:
                return
            colors = self._compute_layer_colors(layer, pts)
            if colors is not None:
                geom.colors = o3d.utility.Vector3dVector(colors)
                self._o3d_scene.remove_geometry(geom_name)
                mat = rendering.MaterialRecord()
                mat.shader = "defaultUnlit"
                mat.point_size = layer.point_size
                self._o3d_scene.add_geometry(geom_name, geom, mat)
        except Exception as exc:
            logger.debug(f"Color update failed for {geom_name}: {exc}")

    def _compute_layer_colors(self, layer: SceneLayer, pts: np.ndarray) -> Optional[np.ndarray]:
        n = len(pts)
        cm = layer.color_mode
        if cm == ColorMode.RGB:
            return None
        elif cm == ColorMode.SINGLE:
            return np.tile(layer.single_color, (n, 1)).astype(np.float64)
        elif cm == ColorMode.ELEVATION:
            z = pts[:, 2]
            return apply_colormap(z, layer.colormap).astype(np.float64)
        elif cm == ColorMode.INTENSITY:
            intensity = layer.attributes.get("intensity")
            if intensity is not None and len(intensity) == n:
                return apply_colormap(intensity, "plasma").astype(np.float64)
        elif cm == ColorMode.CLASSIFICATION:
            cls_ids = layer.attributes.get("classification")
            if cls_ids is not None and len(cls_ids) == n:
                return build_classification_colors(cls_ids).astype(np.float64)
        elif cm == ColorMode.NORMAL:
            if layer.has_geometry and hasattr(layer.geometry, "normals"):
                norms = np.asarray(layer.geometry.normals)
                if len(norms) == n:
                    return np.clip((norms + 1) / 2, 0, 1).astype(np.float64)
        return None

    def _on_point_size_changed(self, val: float):
        for layer in self.scene.get_visible_layers():
            layer.point_size = float(val)
            try:
                mat = self._o3d_scene.get_geometry_material(self._geom_name(layer))
                if mat is not None:
                    mat.point_size = float(val)
                    self._o3d_scene.modify_geometry_material(self._geom_name(layer), mat)
            except Exception:
                pass

    # ---------- Camera ----------

    def _fit_view(self):
        try:
            self._o3d_scene_widget.setup_camera(60, self._o3d_scene.bounding_box, (0, 0, 0))
        except Exception:
            pass

    def _set_view(self, direction: str):
        try:
            bbox = self._o3d_scene.bounding_box
            center = bbox.get_center()
            d = float(np.linalg.norm(bbox.get_max_bound() - bbox.get_min_bound()))
            if direction == "top":
                eye = center + np.array([0, 0, d], dtype=np.float64)
                up = np.array([0, 1, 0], dtype=np.float64)
            elif direction == "front":
                eye = center + np.array([d, 0, 0], dtype=np.float64)
                up = np.array([0, 0, 1], dtype=np.float64)
            elif direction == "side":
                eye = center + np.array([0, d, 0], dtype=np.float64)
                up = np.array([0, 0, 1], dtype=np.float64)
            else:
                return
            self._o3d_scene_widget.look_at(center, eye, up)
        except Exception:
            pass

    # ---------- Export ----------

    def _export_screenshot(self):
        path = filedialog.asksaveasfilename(
            title="导出截图",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return
        try:
            self._o3d_scene_widget.scene.render_to_image(self._o3d_scene_widget.renderer)
            img = self._o3d_scene_widget.renderer.render_to_image()
            o3d.io.write_image(path, img)
            self._status_label.configure(text=f"截图已保存: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def _clear_all(self):
        for layer in list(self.scene.layers):
            try:
                self._o3d_scene.remove_geometry(self._geom_name(layer))
            except Exception:
                pass
        self.scene.clear()
        self.lod_mgr.clear()
        self._refresh_layer_list()
        self._status_label.configure(text="已清除所有图层")

    def _on_close(self):
        try:
            gui.Application.instance.quit()
        except Exception:
            pass
        self.destroy()

    def load_from_resource(self, resource: dict) -> None:
        """Load a resource record into the viewer."""
        path = resource.get("source_path", "")
        source_type = resource.get("source_type", "")
        if not path:
            return
        if source_type == "pointcloud":
            self._load_pointcloud(path)
        elif source_type == "mesh":
            self._load_mesh(path)
        elif source_type == "raster":
            self._load_dem(path)

    # ────────── Processing pipeline ──────────

    def _get_active_pointcloud_layer(self):
        for layer in self.scene.get_visible_layers():
            if layer.layer_type in (LayerType.POINT_CLOUD, LayerType.DEM):
                return layer
        return None

    def _refresh_point_count_display(self):
        layer = self._get_active_pointcloud_layer()
        if layer and layer.has_geometry:
            try:
                n = len(np.asarray(layer.geometry.points))
            except Exception:
                n = layer.point_count
            for child in self._proc_card.winfo_children():
                if isinstance(child, ctk.CTkLabel) and "\u70b9\u4e91\u6570" in (
                    child.cget("text") or ""
                ):
                    child.configure(text=f"\u70b9\u4e91\u6570: {n:,}")
                    break

    def _voxel_downsample(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None:
            return
        try:
            import open3d as o3d

            from core.pointcloud_ops import voxel_downsample as vd

            down = vd(layer.geometry, voxel_size=0.5)
            layer.geometry = down
            layer.point_count = len(np.asarray(down.points))
            geom_name = self._geom_name(layer)
            self._o3d_scene.remove_geometry(geom_name)
            mat = rendering.MaterialRecord()
            mat.shader = "defaultUnlit"
            mat.point_size = layer.point_size
            self._o3d_scene.add_geometry(geom_name, down, mat)
            self._apply_layer_colors(layer)
            self._refresh_point_count_display()
            self._status_label.configure(
                text=f"\u4f53\u7d20\u4e0b\u91c7\u6837\u5b8c\u6210: {layer.point_count:,} \u70b9"
            )
        except Exception as exc:
            logger.error(f"Voxel downsample failed: {exc}")

    def _statistical_filter(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None:
            return
        try:
            from core.pointcloud_ops import statistical_outlier_removal as sorf

            inliers, outliers = sorf(layer.geometry)
            layer.geometry = inliers
            layer.point_count = len(np.asarray(inliers.points))
            geom_name = self._geom_name(layer)
            self._o3d_scene.remove_geometry(geom_name)
            mat = rendering.MaterialRecord()
            mat.shader = "defaultUnlit"
            mat.point_size = layer.point_size
            self._o3d_scene.add_geometry(geom_name, inliers, mat)
            self._apply_layer_colors(layer)
            self._refresh_point_count_display()
            n_out = len(np.asarray(outliers.points))
            self._status_label.configure(
                text=f"\u53bb\u566a\u5b8c\u6210: {layer.point_count:,} \u70b9 (\u79fb\u9664 {n_out:,})"
            )
        except Exception as exc:
            logger.error(f"Statistical filter failed: {exc}")

    def _ground_filter(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None:
            return
        try:
            from core.pointcloud_ops import cloth_simulation_filter as csf

            ground, non_ground = csf(layer.geometry)
            import open3d as o3d

            n_g = len(np.asarray(ground.points))
            n_ng = len(np.asarray(non_ground.points))
            if n_g > 0 and n_ng > 0:
                from core.pointcloud_ops import build_classification_colors

                ground_cls = np.full(n_g, 2, dtype=np.int32)
                non_ground_cls = np.full(n_ng, 1, dtype=np.int32)
                combined_pts = np.vstack(
                    [
                        np.asarray(ground.points, dtype=np.float64),
                        np.asarray(non_ground.points, dtype=np.float64),
                    ]
                )
                combined_cls = np.concatenate([ground_cls, non_ground_cls])
                combined_colors = build_classification_colors(combined_cls)
                new_pcd = o3d.geometry.PointCloud()
                new_pcd.points = o3d.utility.Vector3dVector(combined_pts)
                new_pcd.colors = o3d.utility.Vector3dVector(combined_colors.astype(np.float64))
                layer.geometry = new_pcd
                layer.point_count = len(combined_pts)
                layer.attributes["classification"] = combined_cls
                layer.color_mode = ColorMode.CLASSIFICATION
                geom_name = self._geom_name(layer)
                self._o3d_scene.remove_geometry(geom_name)
                mat = rendering.MaterialRecord()
                mat.shader = "defaultUnlit"
                mat.point_size = layer.point_size
                self._o3d_scene.add_geometry(geom_name, new_pcd, mat)
                self._color_mode_var.set("classification")
            else:
                layer.geometry = ground if n_g > 0 else non_ground
                layer.point_count = max(n_g, n_ng)
                geom_name = self._geom_name(layer)
                self._o3d_scene.remove_geometry(geom_name)
                mat = rendering.MaterialRecord()
                mat.shader = "defaultUnlit"
                mat.point_size = layer.point_size
                self._o3d_scene.add_geometry(geom_name, layer.geometry, mat)
                self._apply_layer_colors(layer)
            self._refresh_point_count_display()
            self._status_label.configure(
                text=f"\u5730\u9762\u6ee4\u6ce2\u5b8c\u6210: \u5730\u9762={n_g:,}, \u975e\u5730\u9762={n_ng:,}"
            )
        except Exception as exc:
            logger.error(f"Ground filter failed: {exc}")

    def _estimate_normals(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None:
            return
        try:
            from core.pointcloud_ops import estimate_normals as en

            layer.geometry = en(layer.geometry)
            layer.color_mode = ColorMode.NORMAL
            self._color_mode_var.set("normal")
            self._apply_layer_colors(layer)
            self._status_label.configure(text="\u6cd5\u7ebf\u4f30\u8ba1\u5b8c\u6210")
        except Exception as exc:
            logger.error(f"Normal estimation failed: {exc}")

    def _open_profile_tool(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None or not layer.has_geometry:
            return
        from tkinter import messagebox, simpledialog

        result = simpledialog.askstring(
            "\u5256\u9762\u5206\u6790",
            "\u8f93\u5165\u6cbf\u7ebf\u7684\u4e24\u70b9\u5750\u6807 (x1,y1,x2,y2):",
            parent=self,
        )
        if not result:
            return
        try:
            parts = [float(v.strip()) for v in result.split(",")]
            if len(parts) != 4:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "\u8f93\u5165\u9519\u8bef",
                "\u8bf7\u8f93\u5165\u56db\u4e2a\u6570\u5b57: x1,y1,x2,y2",
            )
            return
        from .viewer_3d_toolbar import SectionTool

        pts = np.asarray(layer.geometry.points)
        dem = np.column_stack([pts[:, 0], pts[:, 1], pts[:, 2]])
        tool = SectionTool()
        tool.start(np.array([parts[0], parts[1], 0.0]))
        tool.update(np.array([parts[2], parts[3], 0.0]))
        dists, elevs = tool.sample_profile(dem, num_samples=200)
        ProfileDialog(self, dists, elevs, f"\u5256\u9762 - {layer.name}")

    # ────────── Export ──────────

    def _export_las(self):
        layer = self._get_active_pointcloud_layer()
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
            title="\u5bfc\u51fa LAS",
            defaultextension=".las",
            filetypes=[("LAS", "*.las"), ("LAZ", "*.laz")],
        )
        if not path:
            return
        pts = np.asarray(layer.geometry.points).astype(np.float64)
        cls_ids = layer.attributes.get("classification")
        if cls_ids is not None and len(cls_ids) != len(pts):
            cls_ids = None
        try:
            clr = (
                np.asarray(layer.geometry.colors)
                if hasattr(layer.geometry, "has_colors") and layer.geometry.has_colors()
                else None
            )
        except Exception:
            clr = None
        ok = export_las(pts, path, classifications=cls_ids, colors=clr, crs_wkt=layer.crs)
        if ok:
            self._status_label.configure(text=f"\u5df2\u5bfc\u51fa LAS: {Path(path).name}")
        else:
            self._status_label.configure(text="LAS \u5bfc\u51fa\u5931\u8d25")

    def _export_ply(self):
        layer = self._get_active_pointcloud_layer()
        if layer is None or not layer.has_geometry:
            return
        path = filedialog.asksaveasfilename(
            title="\u5bfc\u51fa PLY",
            defaultextension=".ply",
            filetypes=[("PLY", "*.ply")],
        )
        if not path:
            return
        pts = np.asarray(layer.geometry.points).astype(np.float64)
        try:
            clr = (
                np.asarray(layer.geometry.colors)
                if hasattr(layer.geometry, "has_colors") and layer.geometry.has_colors()
                else None
            )
        except Exception:
            clr = None
        ok = export_ply(pts, path, colors=clr)
        if ok:
            self._status_label.configure(text=f"\u5df2\u5bfc\u51fa PLY: {Path(path).name}")
        else:
            self._status_label.configure(text="PLY \u5bfc\u51fa\u5931\u8d25")

    # ────────── State persistence ──────────

    def get_state(self) -> dict:
        return {"scene": self.scene.to_dict()}

    def set_state(self, state: dict) -> None:
        if state and "scene" in state:
            self.scene = SceneGraph.from_dict(state["scene"])
