# ui/vector_tab.py
import os
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import cv2
import numpy as np

from common import utils
from common.config import DEFAULT_VECTOR_COLOR, SELECTED_COLOR
from common.logger import logger
from common.utils import safe_execute, set_chinese_font
from core.spatial_reference import pixel_to_map, read_raster_spatial_ref
from core.vector_processing import (
    add_property_field,
    batch_update_properties,
    create_line_feature,
    create_new_layer,
    create_point_feature,
    create_polygon_feature,
    delete_property_field,
    invalidate_shapely_cache,
    move_feature,
    select_feature,
    update_feature_property,
)
from data.vector_io import read_shp, save_dwg, save_shp

from .error_dialog import show_actionable_error
from .import_preview_dialog import confirm_import
from .raster_viewer import RasterViewer
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard
from .ui_helpers import (
    mark_project_dirty,
    notify,
    raster_geo_transform,
    record_data_source,
    record_project_result,
)
from .undo_manager import DeleteFeatureCommand, EditVertexCommand, MoveFeatureCommand, UndoManager

set_chinese_font()


class VectorTab(ctk.CTkFrame):
    def __init__(self, parent, status_vars):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self.status_vars = status_vars

        # 矢量数据
        self.layers = []
        self.selected_layer_idx = None
        self.selected_feature_idx = None
        self.selected_feature = None

        # 编辑状态
        self.edit_mode = "select"
        self.drawing_points = []
        self.temp_artists = []
        self.move_start = None

        # 橡皮筋
        self._mouse_x = 0
        self._mouse_y = 0
        self._rubber_band = None  # (x1,y1,x2,y2) 当前橡皮筋线段
        self._vertex_drag_idx = None  # 顶点拖拽索引
        self._vertex_old_pos = None

        # 影像底图
        self.base_image = None
        self.base_image_extent = None
        self.base_image_path = ""
        self.base_geo_transform = None
        self.base_crs = ""
        self._viewer_content = ""

        self.undo_mgr = UndoManager(on_change=self._on_undo_state_change)
        self.create_widgets()
        logger.info("矢量编辑标签页初始化完成")

    def _on_undo_state_change(self, can_undo, can_redo):
        """Update status bar with undo/redo state"""
        if "undo" in self.status_vars:
            u = "[Ctrl+Z]" if can_undo else ""
            r = "[Ctrl+Y]" if can_redo else ""
            self.status_vars["undo"].set(f"{u} {r}".strip())

    def create_widgets(self):
        # 1:3 统一布局（和其他标签页完全一致）
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=280)
        self.grid_columnconfigure(1, weight=3)

        # 左侧可滚动控制面板
        self.control_scroll = ctk.CTkScrollableFrame(self, **PANEL_STYLE)
        self.control_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 右侧工作区
        self.canvas_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.canvas_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # ========== 左侧卡片组 ==========
        # 1. 文件操作
        self.file_card = CollapsibleCard(self.control_scroll, "文件操作")
        self.file_card.pack(fill="x", pady=5, padx=5)

        ctk.CTkButton(self.file_card.content, text="加载SHP文件", command=self.load_shp).pack(
            fill="x", pady=3, padx=5
        )
        ctk.CTkButton(
            self.file_card.content, text="新建矢量图层", command=self.new_empty_layer
        ).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(
            self.file_card.content, text="导入影像底图", command=self.load_base_image
        ).pack(fill="x", pady=3, padx=5)

        self.export_fmt = ctk.StringVar(value="shp")
        ctk.CTkOptionMenu(
            self.file_card.content, variable=self.export_fmt, values=["shp", "dwg/dxf"]
        ).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(self.file_card.content, text="导出文件", command=self.export_file).pack(
            fill="x", pady=3, padx=5
        )

        # 2. 编辑工具
        self.edit_card = CollapsibleCard(self.control_scroll, "编辑工具")
        self.edit_card.pack(fill="x", pady=5, padx=5)

        self.tool_var = ctk.StringVar(value="select")
        tools = [
            ("选择要素", "select"),
            ("移动要素", "move"),
            ("绘制点", "draw_point"),
            ("绘制线", "draw_line"),
            ("绘制面", "draw_polygon"),
            ("编辑顶点", "edit_vertices"),
        ]
        for t, v in tools:
            ctk.CTkRadioButton(
                self.edit_card.content,
                text=t,
                variable=self.tool_var,
                value=v,
                command=self.set_edit_mode,
                font=FONT_NORMAL,
            ).pack(anchor="w", pady=2, padx=5)

        ctk.CTkButton(
            self.edit_card.content,
            text="删除选中",
            fg_color=THEME["danger"],
            command=self.delete_selected,
        ).pack(fill="x", pady=5, padx=5)
        ctk.CTkButton(self.edit_card.content, text="清空画布", command=self.clear_all).pack(
            fill="x", pady=3, padx=5
        )

        # 3. 图层管理
        self.layer_card = CollapsibleCard(self.control_scroll, "图层管理")
        self.layer_card.pack(fill="x", pady=5, padx=5)

        # 图层树
        self.layer_tree = ttk.Treeview(
            self.layer_card.content, columns=("name", "type"), show="headings", height=5
        )
        self.layer_tree.heading("name", text="图层名")
        self.layer_tree.heading("type", text="类型")
        self.layer_tree.column("name", width=120)
        self.layer_tree.column("type", width=80)
        self.layer_tree.pack(fill="x", pady=2, padx=5)
        self.layer_tree.bind("<<TreeviewSelect>>", self._on_layer_tree_select)

        # 图层操作按钮
        layer_btn_frame = ctk.CTkFrame(self.layer_card.content, fg_color="transparent")
        layer_btn_frame.pack(fill="x", pady=2, padx=5)
        ctk.CTkButton(layer_btn_frame, text="显示", width=6, command=self.show_layer).pack(
            side="left", padx=1
        )
        ctk.CTkButton(layer_btn_frame, text="隐藏", width=6, command=self.hide_layer).pack(
            side="left", padx=1
        )
        ctk.CTkButton(layer_btn_frame, text="删除", width=6, command=self.delete_layer).pack(
            side="left", padx=1
        )

        # 4. 属性编辑
        self.prop_card = CollapsibleCard(self.control_scroll, "属性编辑")
        self.prop_card.pack(fill="x", pady=5, padx=5)

        self.prop_tree = ttk.Treeview(
            self.prop_card.content, columns=("field", "value"), show="headings", height=6
        )
        self.prop_tree.heading("field", text="字段")
        self.prop_tree.heading("value", text="值")
        self.prop_tree.pack(fill="x", pady=2, padx=5)

        prop_btn_frame = ctk.CTkFrame(self.prop_card.content, fg_color="transparent")
        prop_btn_frame.pack(fill="x", pady=2, padx=5)
        ctk.CTkButton(prop_btn_frame, text="修改", width=6, command=self.edit_prop).pack(
            side="left", padx=1
        )
        ctk.CTkButton(prop_btn_frame, text="新增", width=6, command=self.add_field).pack(
            side="left", padx=1
        )
        ctk.CTkButton(prop_btn_frame, text="删除", width=6, command=self.del_field).pack(
            side="left", padx=1
        )

        ctk.CTkButton(
            self.prop_card.content,
            text="批量赋值",
            fg_color=THEME["accent"],
            command=self.batch_edit_prop,
        ).pack(fill="x", pady=3, padx=5)

        # 提示信息
        self.tip_label = ctk.CTkLabel(
            self.control_scroll,
            text="选择要素查看属性",
            wraplength=250,
            text_color=THEME["text_secondary"],
            font=FONT_SMALL,
        )
        self.tip_label.pack(pady=10, padx=5)

        # ========== RasterViewer ==========
        self.viewer = RasterViewer(
            self.canvas_frame,
            on_coord_change=self._on_viewer_coord,
            on_mouse_down=self.on_mouse_down,
            on_mouse_up=self.on_mouse_up,
            on_mouse_move=self.on_mouse_move,
            on_dblclick=self.on_click,
        )
        self.viewer.pack(fill="both", expand=True, padx=5, pady=5)
        self.after(50, self._ensure_blank_workspace)

        # ========== 图层管理功能 ==========

        # Keyboard shortcuts
        self.master.bind("<Control-z>", lambda e: self.undo_mgr.undo())
        self.master.bind("<Control-y>", lambda e: self.undo_mgr.redo())
        self.master.bind("<Control-Z>", lambda e: self.undo_mgr.redo())
        self.master.bind("<Delete>", lambda e: self.delete_selected())

    def refresh_layer_tree(self):
        """刷新图层树（修复geometry_type缺失问题）"""
        for i in self.layer_tree.get_children():
            self.layer_tree.delete(i)
        for idx, layer in enumerate(self.layers):
            # 兼容不同版本的图层结构
            if "geometry_type" in layer:
                geom_type = layer["geometry_type"]
            elif "type" in layer:
                geom_type = layer["type"]
            elif layer["features"]:
                # 从第一个要素推断类型
                geom_type = layer["features"][0]["geometry"]["type"]
            else:
                geom_type = "空图层"
            self.layer_tree.insert("", "end", values=(layer["name"], geom_type))

    def _on_layer_tree_select(self, _event=None):
        idx = self._selected_tree_layer_index()
        if idx is None:
            return
        self.selected_layer_idx = idx
        self.selected_feature_idx = None
        self.selected_feature = None
        self.refresh_prop()
        self.status_vars["features"].set("无选中")

    def _selected_tree_layer_index(self):
        sel = self.layer_tree.selection()
        if not sel:
            return None
        idx = int(self.layer_tree.index(sel[0]))
        return idx if 0 <= idx < len(self.layers) else None

    def _layer_geometry_type(self, layer):
        if "geometry_type" in layer:
            return layer["geometry_type"]
        schema = layer.get("schema") or {}
        if schema.get("geometry"):
            return schema["geometry"]
        if layer.get("type"):
            return layer["type"]
        if layer.get("features"):
            return layer["features"][0].get("geometry", {}).get("type", "")
        return ""

    def _ensure_draw_layer(self, geom_type, default_name):
        idx = self._selected_tree_layer_index()
        if idx is not None and self._layer_geometry_type(self.layers[idx]) == geom_type:
            self.selected_layer_idx = idx
            return idx, self.layers[idx]
        if (
            self.selected_layer_idx is not None
            and 0 <= self.selected_layer_idx < len(self.layers)
            and self._layer_geometry_type(self.layers[self.selected_layer_idx]) == geom_type
        ):
            return self.selected_layer_idx, self.layers[self.selected_layer_idx]
        for i, layer in enumerate(self.layers):
            if self._layer_geometry_type(layer) == geom_type:
                self.selected_layer_idx = i
                return i, layer

        layer = create_new_layer(default_name, geom_type)
        layer["visible"] = True
        layer["color"] = DEFAULT_VECTOR_COLOR
        layer["geometry_type"] = geom_type
        layer["coord_mode"] = "pixel"
        self.layers.append(layer)
        self.refresh_layer_tree()
        self.selected_layer_idx = len(self.layers) - 1
        return len(self.layers) - 1, layer

    def _ensure_blank_workspace(self):
        if self.base_image is None and self.viewer._pil_image is None:
            self.viewer.load_blank()
            self._viewer_content = "blank"

    def show_layer(self):
        """显示选中图层"""
        sel = self.layer_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请选择图层")
            return
        idx = int(self.layer_tree.index(sel[0]))
        self.layers[idx]["visible"] = True
        self.redraw()

    def hide_layer(self):
        """隐藏选中图层"""
        sel = self.layer_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请选择图层")
            return
        idx = int(self.layer_tree.index(sel[0]))
        self.layers[idx]["visible"] = False
        self.redraw()

    def delete_layer(self):
        """删除选中图层（修复：删除后重置选中状态）"""
        sel = self.layer_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请选择图层")
            return
        idx = int(self.layer_tree.index(sel[0]))
        if messagebox.askyesno("确认", f"确定删除图层 {self.layers[idx]['name']} 吗？"):
            del self.layers[idx]
            # 关键修复：删除图层后重置所有选中状态
            self._reset_selection()
            self.refresh_layer_tree()
            self.redraw()
            mark_project_dirty(self)

    # ========== 编辑功能 ==========
    def set_edit_mode(self):
        self.edit_mode = self.tool_var.get()
        self.drawing_points = []
        self.clear_temp()
        tips = {
            "select": "点击选择要素",
            "move": "拖动移动要素",
            "draw_point": "点击绘制点",
            "draw_line": "左键加点 右键取消 双击结束",
            "draw_polygon": "左键加点 右键取消 双击闭合",
            "edit_vertices": "先选择要素 再拖拽顶点调整形状",
        }
        self.tip_label.configure(text=tips[self.edit_mode])
        self.status_vars["algorithm"].set(f"编辑模式: {self.edit_mode}")

    def clear_temp(self):
        self.drawing_points = []
        self.redraw()

    def _reset_selection(self):
        """重置所有选中状态（关键修复）"""
        self.selected_layer_idx = None
        self.selected_feature_idx = None
        self.selected_feature = None
        self.refresh_prop()
        self.status_vars["features"].set("无选中")

    @safe_execute
    def load_shp(self):
        p = filedialog.askopenfilename(filetypes=[("SHP文件", "*.shp")])
        if p and confirm_import(self, p, "shp"):
            self.load_shp_direct(p, preview=False)

    @safe_execute
    def load_shp_direct(self, p, preview: bool = True):
        if preview and not confirm_import(self, p, "shp"):
            return
        try:
            layer = read_shp(p)
            layer["name"] = os.path.basename(p).replace(".shp", "")
            layer["path"] = p
            layer["visible"] = True
            layer["color"] = DEFAULT_VECTOR_COLOR
            layer["coord_mode"] = "map"
            self.layers.append(layer)
            record_data_source(self, p, "vector")
            self.refresh_layer_tree()
            self.redraw()
            self.status_vars["image_size"].set(f"图层数: {len(self.layers)}")
            mark_project_dirty(self)
            notify(self, f"SHP 文件加载完成：{os.path.basename(p)}", "success")
        except Exception as exc:
            show_actionable_error(
                self,
                "SHP 加载失败",
                "矢量文件没有成功导入。",
                "请确认 .shp/.dbf/.shx 等配套文件完整，并检查坐标系信息。",
                detail=str(exc),
            )

    @safe_execute
    def new_empty_layer(self):
        layer_type = ctk.CTkInputDialog(
            text="请选择新建图层类型（点/线/面）", title="新建矢量图层"
        ).get_input()
        if not layer_type or layer_type not in ["点", "线", "面"]:
            messagebox.showwarning("提示", "请输入正确的图层类型：点/线/面")
            return

        geom_map = {"点": "Point", "线": "LineString", "面": "Polygon"}
        name_map = {"点": "点图层", "线": "线图层", "面": "面图层"}

        new_layer = create_new_layer(name_map[layer_type], geom_map[layer_type])
        new_layer["visible"] = True
        new_layer["color"] = DEFAULT_VECTOR_COLOR
        new_layer["geometry_type"] = geom_map[layer_type]  # 明确添加geometry_type字段
        new_layer["coord_mode"] = "pixel"
        self.layers.append(new_layer)
        self.refresh_layer_tree()
        self.redraw()
        mark_project_dirty(self)
        notify(self, f"已新建{layer_type}图层", "success")

    @safe_execute
    def load_base_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff")]
        )
        if not path:
            return
        if not confirm_import(self, path, "image"):
            return

        img = utils.imread_chinese(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]

        self.base_image_path = path
        self.base_image = img
        self.base_image_extent = [0, w, 0, h]  # 修复：使用正确的坐标范围
        source = record_data_source(self, path, "raster")
        self.base_geo_transform = (source or {}).get("transform") or raster_geo_transform(path)
        self.base_crs = (source or {}).get("crs") or ""
        self.viewer.load(image_array=self.base_image, geo_transform=self.base_geo_transform)
        self._viewer_content = self.base_image_path
        self.redraw()
        self.status_vars["image_size"].set(f"底图: {w}×{h}")
        mark_project_dirty(self)
        notify(self, f"影像底图导入完成：{os.path.basename(path)}", "success")

    def _on_viewer_coord(self, text):
        if "coords" in self.status_vars:
            self.status_vars["coords"].set(text or "")

    def redraw(self):
        self.viewer.clear_overlays()

        if self.base_image is not None and self._viewer_content != self.base_image_path:
            self.viewer.load(image_array=self.base_image, geo_transform=self.base_geo_transform)
            self._viewer_content = self.base_image_path
        elif self.base_image is None and self.viewer._pil_image is None:
            self._ensure_blank_workspace()

        # vector layers
        for layer in self.layers:
            if not layer["visible"]:
                continue
            clr = layer["color"]
            for f in layer["features"]:
                g = f["geometry"]
                if g["type"] == "Point":
                    x, y = g["coordinates"]
                    self.viewer.add_point(x, y, color=clr, radius=6)
                elif g["type"] == "LineString":
                    self.viewer.add_line(g["coordinates"], color=clr, width=2)
                elif g["type"] == "Polygon":
                    self.viewer.add_polygon(g["coordinates"][0], color=clr, fill=clr, width=2)

        # selected feature
        if self.selected_feature:
            g = self.selected_feature["geometry"]
            if g["type"] == "Point":
                x, y = g["coordinates"]
                self.viewer.add_point(x, y, color="red", radius=8, label="Selected")
            elif g["type"] == "LineString":
                self.viewer.add_line(g["coordinates"], color="red", width=3)
            elif g["type"] == "Polygon":
                self.viewer.add_polygon(g["coordinates"][0], color="red", width=2)

        # 顶点编辑模式：显示所有顶点
        if self.edit_mode == "edit_vertices" and self.selected_feature:
            for idx, (vx, vy) in enumerate(self._get_vertices(self.selected_feature)):
                self.viewer.add_rect(
                    vx - 4, vy - 4, vx + 4, vy + 4, color="#ffaa00", width=2, label=str(idx)
                )

        # temp drawing points + rubber-band
        if self.drawing_points:
            for px, py in self.drawing_points:
                self.viewer.add_point(px, py, color="red", radius=5)
            if len(self.drawing_points) > 1:
                self.viewer.add_line(self.drawing_points, color="red", width=1)
            # 橡皮筋：最后一点到鼠标位置
            lx, ly = self.drawing_points[-1]
            self.viewer.add_line(
                [(lx, ly), (self._mouse_x, self._mouse_y)], color="#ff6600", width=1
            )

        self.viewer.render()
        self.refresh_prop()

    def refresh_prop(self):
        for i in self.prop_tree.get_children():
            self.prop_tree.delete(i)
        if not self.selected_feature:
            return
        for k, v in self.selected_feature["properties"].items():
            self.prop_tree.insert("", "end", values=(k, v))
        self.status_vars["features"].set(f"选中: 1个要素")

    def edit_prop(self):
        sel = self.prop_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请选中属性行")
            return
        field, old = self.prop_tree.item(sel[0], "values")
        val = ctk.CTkInputDialog(text=f"输入{field}新值", title="修改属性").get_input()
        if val is None:
            return
        self.selected_feature = update_feature_property(self.selected_feature, field, val)
        self.layers[self.selected_layer_idx]["features"][
            self.selected_feature_idx
        ] = self.selected_feature
        invalidate_shapely_cache(self.layers[self.selected_layer_idx], self.selected_feature_idx)
        self.refresh_prop()
        mark_project_dirty(self)

    def add_field(self):
        if self.selected_layer_idx is None:
            messagebox.showwarning("提示", "请先选中图层")
            return
        name = ctk.CTkInputDialog(text="输入字段名", title="新增属性字段").get_input()
        if not name:
            return
        self.layers[self.selected_layer_idx] = add_property_field(
            self.layers[self.selected_layer_idx], name
        )
        self.refresh_prop()
        mark_project_dirty(self)

    def del_field(self):
        if self.selected_layer_idx is None:
            messagebox.showwarning("提示", "请先选中图层")
            return
        sel = self.prop_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请选中字段")
            return
        field = self.prop_tree.item(sel[0], "values")[0]
        self.layers[self.selected_layer_idx] = delete_property_field(
            self.layers[self.selected_layer_idx], field
        )
        self.refresh_prop()
        mark_project_dirty(self)

    def batch_edit_prop(self):
        if self.selected_layer_idx is None:
            messagebox.showwarning("提示", "请先选中图层")
            return
        field = ctk.CTkInputDialog(text="输入要批量赋值的字段名", title="批量编辑").get_input()
        val = ctk.CTkInputDialog(text="输入统一值", title="批量赋值").get_input()
        if not field or val is None:
            return
        self.layers[self.selected_layer_idx] = batch_update_properties(
            self.layers[self.selected_layer_idx], field, val
        )
        self.refresh_prop()
        self.redraw()
        mark_project_dirty(self)

    # ========== 导出功能 ==========
    @safe_execute
    def export_file(self):
        if not self.layers:
            messagebox.showwarning("提示", "无数据导出")
            return
        fmt = self.export_fmt.get()
        ext = ".shp" if fmt == "shp" else ".dxf"
        path = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(fmt, f"*{ext}")])
        if not path:
            return
        layer = (
            self.layers[self.selected_layer_idx]
            if self.selected_layer_idx != None
            else self.layers[0]
        )
        layer = self._prepare_layer_for_export(layer)
        if fmt == "shp":
            save_shp(layer, path)
        else:
            save_dwg(layer, path)
        record_project_result(
            self,
            "vector",
            "导出矢量文件",
            inputs=[self.base_image_path, *[lyr.get("path", "") for lyr in self.layers]],
            outputs=[path],
            params={"format": fmt},
            metrics={
                "layers": len(self.layers),
                "features": sum(len(lyr.get("features", [])) for lyr in self.layers),
            },
        )
        notify(self, f"导出 {fmt} 完成：{path}", "success")

    def _prepare_layer_for_export(self, layer):
        import copy

        out = copy.deepcopy(layer)
        if out.get("coord_mode") == "map":
            return out
        if self.base_geo_transform:
            for feature in out.get("features", []):
                self._transform_feature_coords(feature, self._pixel_to_map_point)
            if self.base_crs:
                out["crs"] = self.base_crs
            out["coord_mode"] = "map"
            return out
        if self.base_image is not None:
            height = self.base_image.shape[0]
            for feature in out.get("features", []):
                self._transform_feature_coords(feature, lambda x, y: (x, height - y))
        return out

    def _pixel_to_map_point(self, x, y):
        mapped = pixel_to_map(x, y, self.base_geo_transform)
        return mapped if mapped else (x, y)

    def _transform_feature_coords(self, feature, transform_point):
        geometry = feature.get("geometry", {})
        gtype = geometry.get("type")
        if gtype == "Point":
            x, y = geometry["coordinates"][:2]
            geometry["coordinates"] = list(transform_point(x, y))
        elif gtype in ("LineString", "MultiPoint"):
            geometry["coordinates"] = [transform_point(x, y) for x, y in geometry["coordinates"]]
        elif gtype == "Polygon":
            geometry["coordinates"] = [
                [transform_point(x, y) for x, y in ring] for ring in geometry["coordinates"]
            ]
        elif gtype == "MultiLineString":
            geometry["coordinates"] = [
                [transform_point(x, y) for x, y in line] for line in geometry["coordinates"]
            ]
        elif gtype == "MultiPolygon":
            geometry["coordinates"] = [
                [[transform_point(x, y) for x, y in ring] for ring in poly]
                for poly in geometry["coordinates"]
            ]

    # ========== 鼠标事件 ==========
    def on_mouse_down(self, px, py, event):
        # 右键取消绘制
        if isinstance(event, dict) and event.get("type") == "right":
            if self.edit_mode in ["draw_line", "draw_polygon"]:
                self.drawing_points = []
                self.clear_temp()
            return

        if self.edit_mode == "select":
            self._select(px, py)
        elif self.edit_mode == "edit_vertices":
            if self.selected_feature:
                idx = self._find_nearest_vertex(px, py)
                if idx is not None:
                    self._vertex_drag_idx = idx
                    verts = self._get_vertices(self.selected_feature)
                    self._vertex_old_pos = verts[idx] if 0 <= idx < len(verts) else None
                    self.move_start = (px, py)
                else:
                    self._select(px, py)
            else:
                self._select(px, py)
        elif self.edit_mode == "move":
            self.move_start = (px, py)
        elif self.edit_mode == "draw_point":
            self._add_point(px, py)
        elif self.edit_mode in ["draw_line", "draw_polygon"]:
            self.drawing_points.append((px, py))
            self._update_temp()

    def on_mouse_move(self, px, py, event):
        # 跟踪鼠标位置（橡皮筋用）
        self._mouse_x, self._mouse_y = px, py

        # 绘制模式下的橡皮筋
        if self.edit_mode in ["draw_line", "draw_polygon"] and self.drawing_points:
            self.redraw()
            return

        # 移动模式
        if not (
            self.edit_mode == "move"
            and self.selected_feature
            and self.move_start
            and self.selected_layer_idx is not None
            and self.selected_feature_idx is not None
            and 0 <= self.selected_layer_idx < len(self.layers)
            and 0
            <= self.selected_feature_idx
            < len(self.layers[self.selected_layer_idx]["features"])
        ):
            return

        # 顶点编辑拖拽
        if (
            self.edit_mode == "edit_vertices"
            and self._vertex_drag_idx is not None
            and self.selected_feature
        ):
            verts = self._get_vertices(self.selected_feature)
            if 0 <= self._vertex_drag_idx < len(verts):
                self._set_vertex_position(self.selected_feature, self._vertex_drag_idx, [px, py])
                self.layers[self.selected_layer_idx]["features"][
                    self.selected_feature_idx
                ] = self.selected_feature
                invalidate_shapely_cache(
                    self.layers[self.selected_layer_idx], self.selected_feature_idx
                )
            self.redraw()
            return

        dx, dy = px - self.move_start[0], py - self.move_start[1]
        if dx == 0 and dy == 0:
            return
        cmd = MoveFeatureCommand(
            self.layers[self.selected_layer_idx], self.selected_feature_idx, dx, dy, self.redraw
        )
        self.undo_mgr.execute(cmd)
        self.selected_feature = self.layers[self.selected_layer_idx]["features"][
            self.selected_feature_idx
        ]
        self.move_start = (px, py)
        self.redraw()

    def on_mouse_up(self, px, py, event):
        if self.edit_mode in ("move", "edit_vertices"):
            if (
                self.edit_mode == "edit_vertices"
                and self._vertex_drag_idx is not None
                and self._vertex_old_pos is not None
                and self.selected_layer_idx is not None
                and self.selected_feature_idx is not None
            ):
                verts = self._get_vertices(self.selected_feature)
                if 0 <= self._vertex_drag_idx < len(verts):
                    new_pos = verts[self._vertex_drag_idx]
                    if tuple(self._vertex_old_pos) != tuple(new_pos):
                        cmd = EditVertexCommand(
                            self.layers[self.selected_layer_idx],
                            self.selected_feature_idx,
                            self._vertex_drag_idx,
                            self._vertex_old_pos,
                            new_pos,
                            self.selected_feature["geometry"]["type"],
                            self.redraw,
                        )
                        self.undo_mgr.record_applied(cmd)
            self.move_start = None
            self._vertex_drag_idx = None
            self._vertex_old_pos = None

    def on_click(self, px, py):
        if self.edit_mode == "draw_line" and len(self.drawing_points) >= 2:
            self._finish_line()
        elif self.edit_mode == "draw_polygon" and len(self.drawing_points) >= 3:
            self._finish_poly()

    def _get_vertices(self, feature):
        """获取要素的所有顶点坐标列表"""
        g = feature["geometry"]
        if g["type"] == "Point":
            return [tuple(g["coordinates"])]
        elif g["type"] == "LineString":
            return [tuple(c) for c in g["coordinates"]]
        elif g["type"] == "Polygon":
            return [tuple(c) for c in g["coordinates"][0]]
        return []

    def _set_vertex_position(self, feature, vertex_idx, pos):
        g = feature["geometry"]
        pos = list(pos)
        if g["type"] == "Point":
            g["coordinates"] = pos
        elif g["type"] == "LineString":
            g["coordinates"][vertex_idx] = pos
        elif g["type"] == "Polygon":
            ring = g["coordinates"][0]
            ring[vertex_idx] = pos
            if vertex_idx == 0 and len(ring) > 1:
                ring[-1] = pos.copy()
            elif vertex_idx == len(ring) - 1 and len(ring) > 1:
                ring[0] = pos.copy()

    def _find_nearest_vertex(self, x, y, tolerance=10):
        """找到选中要素中距离(x,y)最近的顶点索引"""
        if not self.selected_feature:
            return None
        verts = self._get_vertices(self.selected_feature)
        best_idx, best_dist = None, tolerance
        for i, (vx, vy) in enumerate(verts):
            d = ((vx - x) ** 2 + (vy - y) ** 2) ** 0.5
            if d < best_dist:
                best_dist, best_idx = d, i
        return best_idx

    def _select(self, x, y):
        self.selected_layer_idx, self.selected_feature_idx, self.selected_feature = select_feature(
            self.layers, x, y
        )
        self.redraw()
        if self.selected_feature:
            self.status_vars["features"].set(f"选中: 1个要素")
        else:
            self.status_vars["features"].set("无选中")

    def _add_point(self, x, y):
        layer_idx, layer = self._ensure_draw_layer("Point", "点图层")
        layer["features"].append(create_point_feature(x, y))
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")
        invalidate_shapely_cache(layer)
        mark_project_dirty(self)

    def _update_temp(self):
        self.redraw()

    def _finish_line(self):
        layer_idx, layer = self._ensure_draw_layer("LineString", "线图层")
        layer["features"].append(create_line_feature(self.drawing_points))
        self.drawing_points = []
        self.clear_temp()
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")
        invalidate_shapely_cache(layer)
        mark_project_dirty(self)

    def _finish_poly(self):
        layer_idx, layer = self._ensure_draw_layer("Polygon", "面图层")
        layer["features"].append(create_polygon_feature(self.drawing_points))
        self.drawing_points = []
        self.clear_temp()
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")
        invalidate_shapely_cache(layer)
        mark_project_dirty(self)

    @safe_execute
    def delete_selected(self):
        if not self.selected_feature or self.selected_layer_idx is None:
            return
        cmd = DeleteFeatureCommand(
            self.layers[self.selected_layer_idx],
            self.selected_feature_idx,
            self.selected_feature,
            self.redraw,
        )
        self.undo_mgr.execute(cmd)
        self._reset_selection()
        self.redraw()
        self.status_vars["features"].set(
            f"Total features: {sum(len(layer['features']) for layer in self.layers)}"
        )
        mark_project_dirty(self)

    def clear_all(self):
        if messagebox.askyesno("确认", "清空所有数据？"):
            self.layers = []
            # 关键修复：清空后重置选中状态
            self._reset_selection()
            self.base_image = None
            self.base_image_extent = None
            self.base_image_path = ""
            self.base_geo_transform = None
            self.base_crs = ""
            self._viewer_content = ""
            self.viewer.clear_image()
            self._ensure_blank_workspace()
            self.refresh_layer_tree()
            self.redraw()
            self.status_vars["image_size"].set("无数据")
            self.status_vars["features"].set("0")
            mark_project_dirty(self)

    # ========== 项目状态管理 ==========

    def destroy(self):
        """Clean up resources to prevent memory leaks"""
        try:
            import matplotlib.pyplot as plt

            plt.close("all")
        except Exception:
            pass
        try:
            if hasattr(self, "canvas") and self.canvas:
                self.canvas = None
        except Exception:
            pass
        super().destroy()

    def get_state(self):
        """获取当前标签页状态，用于保存项目"""
        return {
            "base_image_path": self.base_image_path,
            "layer_paths": [layer.get("path", "") for layer in self.layers],
        }

    def set_state(self, state):
        """从项目文件恢复状态"""
        if not state:
            return

        # 加载底图
        base_path = state.get("base_image_path", "")
        if base_path and os.path.exists(base_path):
            try:
                self.base_image_path = base_path
                img = utils.imread_chinese(base_path)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w = img.shape[:2]
                self.base_image = img
                self.base_image_extent = [0, w, 0, h]
                self.base_geo_transform = raster_geo_transform(base_path)
                self.base_crs = read_raster_spatial_ref(base_path).crs
            except Exception:
                logger.debug("忽略非关键错误")
                pass

        # 加载矢量图层
        layer_paths = state.get("layer_paths", [])
        self.layers = []
        for path in layer_paths:
            if path and os.path.exists(path):
                try:
                    layer = read_shp(path)
                    layer["name"] = os.path.basename(path).replace(".shp", "")
                    layer["path"] = path
                    layer["visible"] = True
                    layer["color"] = DEFAULT_VECTOR_COLOR
                    layer["coord_mode"] = "map"
                    self.layers.append(layer)
                except Exception:
                    pass

        self.refresh_layer_tree()
        self.redraw()
