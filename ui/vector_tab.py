# ui/vector_tab.py
import os
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.patches import Polygon

from common.config import DEFAULT_VECTOR_COLOR, SELECTED_COLOR
from common.logger import logger
from common.utils import safe_execute, set_chinese_font
from core import (
    add_property_field,
    batch_update_properties,
    create_line_feature,
    create_new_layer,
    create_point_feature,
    create_polygon_feature,
    delete_property_field,
    move_feature,
    select_feature,
    update_feature_property,
)
from data import read_shp, save_dwg, save_shp

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard

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

        # 影像底图
        self.base_image = None
        self.base_image_extent = None
        self.base_image_path = ""

        self.create_widgets()
        logger.info("矢量编辑标签页初始化完成")

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

        # ========== 右侧画布 ==========
        self.fig, self.ax = plt.subplots(figsize=(12, 8), dpi=100, facecolor=THEME["panel"])
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.ax.set_facecolor(THEME["panel"])

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.canvas_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

        self.mpl_toolbar = NavigationToolbar2Tk(self.canvas, self.canvas_frame)
        self.mpl_toolbar.config(background=THEME["panel"])
        self.mpl_toolbar.update()

        # 绑定鼠标事件
        self.canvas.mpl_connect("button_press_event", self.on_mouse_down)
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
        self.canvas.mpl_connect("button_release_event", self.on_mouse_up)
        self.canvas.mpl_connect("button_press_event", self.on_click)

    # ========== 图层管理功能 ==========
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

    # ========== 编辑功能 ==========
    def set_edit_mode(self):
        self.edit_mode = self.tool_var.get()
        self.drawing_points = []
        self.clear_temp()
        tips = {
            "select": "点击选择要素",
            "move": "拖动移动要素",
            "draw_point": "点击绘制点",
            "draw_line": "双击结束绘制",
            "draw_polygon": "双击闭合面",
        }
        self.tip_label.configure(text=tips[self.edit_mode])
        self.status_vars["algorithm"].set(f"编辑模式: {self.edit_mode}")

    def clear_temp(self):
        for a in self.temp_artists:
            a.remove()
        self.temp_artists = []
        self.canvas.draw()

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
        if p:
            layer = read_shp(p)
            layer["name"] = os.path.basename(p).replace(".shp", "")
            layer["path"] = p
            layer["visible"] = True
            layer["color"] = DEFAULT_VECTOR_COLOR
            self.layers.append(layer)
            self.refresh_layer_tree()
            self.redraw()
            self.status_vars["image_size"].set(f"图层数: {len(self.layers)}")
            messagebox.showinfo("成功", "SHP文件加载完成")

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
        self.layers.append(new_layer)
        self.refresh_layer_tree()
        self.redraw()
        messagebox.showinfo("成功", f"已新建{layer_type}图层")

    @safe_execute
    def load_base_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff")]
        )
        if not path:
            return

        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]

        self.base_image_path = path
        self.base_image = img
        self.base_image_extent = [0, w, 0, h]  # 修复：使用正确的坐标范围
        self.redraw()
        self.status_vars["image_size"].set(f"底图: {w}×{h}")
        messagebox.showinfo("成功", "影像底图导入完成")

    def redraw(self):
        self.ax.clear()
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.ax.set_facecolor(THEME["panel"])

        # 绘制底图
        if self.base_image is not None and self.base_image_extent is not None:
            self.ax.imshow(self.base_image, extent=self.base_image_extent, aspect="auto", alpha=0.8)

        # 绘制矢量图层
        for layer in self.layers:
            if not layer["visible"]:
                continue
            c = layer["color"]
            for f in layer["features"]:
                g = f["geometry"]
                if g["type"] == "Point":
                    x, y = g["coordinates"]
                    self.ax.plot(x, y, "o", color=c, ms=6)
                elif g["type"] == "LineString":
                    coords = np.array(g["coordinates"])
                    self.ax.plot(coords[:, 0], coords[:, 1], color=c, lw=2)
                elif g["type"] == "Polygon":
                    coords = np.array(g["coordinates"][0])
                    self.ax.add_patch(Polygon(coords, fc=c, alpha=0.4, ec="black"))

        # 高亮选中要素
        if self.selected_feature:
            g = self.selected_feature["geometry"]
            if g["type"] == "Point":
                self.ax.plot(g["coordinates"][0], g["coordinates"][1], "ro", ms=10)
            elif g["type"] == "LineString":
                self.ax.plot(
                    np.array(g["coordinates"])[:, 0], np.array(g["coordinates"])[:, 1], "r", lw=3
                )
            elif g["type"] == "Polygon":
                self.ax.add_patch(Polygon(np.array(g["coordinates"][0]), ec="red", fc="none", lw=2))

        self.canvas.draw()
        self.refresh_prop()

    # ========== 属性表功能 ==========
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
        self.refresh_prop()

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
        if fmt == "shp":
            save_shp(layer, path)
        else:
            save_dwg(layer, path)
        messagebox.showinfo("成功", f"导出{fmt}完成")

    # ========== 鼠标事件 ==========
    def on_mouse_down(self, e):
        if e.inaxes != self.ax:
            return
        x, y = e.xdata, e.ydata
        if e.button == 3:
            self.drawing_points = []
            self.clear_temp()
            return
        if self.edit_mode == "select":
            self._select(x, y)
        elif self.edit_mode == "move":
            self.move_start = (x, y)
        elif self.edit_mode == "draw_point":
            self._add_point(x, y)
        elif self.edit_mode in ["draw_line", "draw_polygon"]:
            self.drawing_points.append((x, y))
            self._update_temp()

    def on_mouse_move(self, e):
        # 关键修复：添加严格的存在性检查
        if not (
            self.edit_mode == "move"
            and self.selected_feature
            and self.move_start
            and e.inaxes
            and self.selected_layer_idx is not None
            and self.selected_feature_idx is not None
            and 0 <= self.selected_layer_idx < len(self.layers)
            and 0
            <= self.selected_feature_idx
            < len(self.layers[self.selected_layer_idx]["features"])
        ):
            return

        dx, dy = e.xdata - self.move_start[0], e.ydata - self.move_start[1]
        self.selected_feature = move_feature(self.selected_feature, dx, dy)
        self.layers[self.selected_layer_idx]["features"][
            self.selected_feature_idx
        ] = self.selected_feature
        self.move_start = (e.xdata, e.ydata)
        self.redraw()

    def on_mouse_up(self, e):
        if self.edit_mode == "move":
            self.move_start = None

    def on_click(self, e):
        if e.dblclick and e.inaxes:
            if self.edit_mode == "draw_line" and len(self.drawing_points) >= 2:
                self._finish_line()
            elif self.edit_mode == "draw_polygon" and len(self.drawing_points) >= 3:
                self._finish_poly()

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
        if not self.layers:
            self.layers.append(create_new_layer("点图层", "Point"))
            self.layers[0]["color"] = DEFAULT_VECTOR_COLOR
            self.layers[0]["geometry_type"] = "Point"
            self.refresh_layer_tree()
        self.layers[0]["features"].append(create_point_feature(x, y))
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")

    def _update_temp(self):
        self.clear_temp()
        for px, py in self.drawing_points:
            (p,) = self.ax.plot(px, py, "ro", ms=5)
            self.temp_artists.append(p)
        if len(self.drawing_points) > 1:
            (l,) = self.ax.plot(
                np.array(self.drawing_points)[:, 0], np.array(self.drawing_points)[:, 1], "r-"
            )
            self.temp_artists.append(l)
        self.canvas.draw()

    def _finish_line(self):
        if not self.layers:
            self.layers.append(create_new_layer("线图层", "LineString"))
            self.layers[0]["color"] = DEFAULT_VECTOR_COLOR
            self.layers[0]["geometry_type"] = "LineString"
            self.refresh_layer_tree()
        self.layers[0]["features"].append(create_line_feature(self.drawing_points))
        self.drawing_points = []
        self.clear_temp()
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")

    def _finish_poly(self):
        if not self.layers:
            self.layers.append(create_new_layer("面图层", "Polygon"))
            self.layers[0]["color"] = DEFAULT_VECTOR_COLOR
            self.layers[0]["geometry_type"] = "Polygon"
            self.refresh_layer_tree()
        self.layers[0]["features"].append(create_polygon_feature(self.drawing_points))
        self.drawing_points = []
        self.clear_temp()
        self.redraw()
        self.status_vars["features"].set(f"总要素: {sum(len(l['features']) for l in self.layers)}")

    @safe_execute
    def delete_selected(self):
        if self.selected_feature:
            self.layers[self.selected_layer_idx]["features"].pop(self.selected_feature_idx)
            # 关键修复：删除要素后重置选中状态
            self._reset_selection()
            self.redraw()
            self.status_vars["features"].set(
                f"总要素: {sum(len(l['features']) for l in self.layers)}"
            )

    @safe_execute
    def clear_all(self):
        if messagebox.askyesno("确认", "清空所有数据？"):
            self.layers = []
            # 关键修复：清空后重置选中状态
            self._reset_selection()
            self.base_image = None
            self.base_image_extent = None
            self.base_image_path = ""
            self.refresh_layer_tree()
            self.redraw()
            self.status_vars["image_size"].set("无数据")
            self.status_vars["features"].set("0")

    # ========== 项目状态管理 ==========
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
                img = cv2.imread(base_path)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w = img.shape[:2]
                self.base_image = img
                self.base_image_extent = [0, w, 0, h]
            except Exception:
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
                    self.layers.append(layer)
                except:
                    pass

        self.refresh_layer_tree()
        self.redraw()
