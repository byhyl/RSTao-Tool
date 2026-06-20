# ui/match_tab.py
import os
import warnings
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from core.image_matching import ImageMatchingCore
from data.image_io import get_image_metadata, save_geotiff_like

from .raster_viewer import RasterViewer
from .settings_manager import load_settings
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard
from .ui_helpers import (
    make_button,
    mark_project_dirty,
    notify,
    raster_geo_transform,
    record_data_source,
    record_project_result,
)

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
warnings.filterwarnings("ignore", category=UserWarning)

DEFAULT_MATCH_THRESHOLD = 0.7
DEFAULT_NMS_RADIUS = 3


class MatchTab(ctk.CTkFrame):
    def __init__(self, parent, status_vars):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self.status_vars = status_vars
        self.core = ImageMatchingCore()

        self.templates = []
        self.template_paths = []
        self.template_geo_transforms = []
        self.search_path = ""
        self.search_geo_transform = None
        self.search_img = None
        self.result_img = None
        self.correlation_map = None
        self.colors = self.core.colors
        self._defaults = load_settings().get("defaults", {})

        self._create_widgets()

    def _create_widgets(self):
        # 1:3 统一布局
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=280)
        self.grid_columnconfigure(1, weight=3)

        # 左侧可滚动控制面板
        self.control_scroll = ctk.CTkScrollableFrame(self, **PANEL_STYLE)
        self.control_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 右侧图像显示区
        self.image_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.image_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.build_control()
        self.build_display()

    def build_control(self):
        # 1. 目标管理卡片
        self.template_card = CollapsibleCard(self.control_scroll, "目标窗口管理")
        self.template_card.pack(fill="x", pady=5, padx=5)

        make_button(
            self.template_card.content, "添加目标窗口", self.add_template, "primary", icon="open"
        ).pack(fill="x", pady=3, padx=5)
        btn_row = ctk.CTkFrame(self.template_card.content, fg_color="transparent")
        btn_row.pack(fill="x", pady=3, padx=5)
        make_button(
            btn_row, "删除选中", self.remove_selected_template, "secondary", width=96, height=30
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        make_button(btn_row, "清空", self.clear_all_templates, "danger", width=72, height=30).pack(
            side="right", fill="x", expand=True, padx=(3, 0)
        )

        self.template_tree = ttk.Treeview(
            self.template_card.content,
            columns=("name", "size"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure(
            "RSTao.Treeview",
            background=THEME["card"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["card"],
            borderwidth=0,
            rowheight=24,
        )
        style.configure(
            "RSTao.Treeview.Heading",
            background=THEME["panel"],
            foreground=THEME["text_secondary"],
            borderwidth=0,
        )
        style.map("RSTao.Treeview", background=[("selected", THEME["accent"])])
        self.template_tree.configure(style="RSTao.Treeview")
        self.template_tree.heading("name", text="模板")
        self.template_tree.heading("size", text="尺寸")
        self.template_tree.column("name", width=150)
        self.template_tree.column("size", width=70, anchor="center")
        self.template_tree.pack(fill="x", pady=5, padx=5)
        self.template_tree.bind("<<TreeviewSelect>>", lambda _e: self._update_display())

        # 2. 搜索区域卡片
        self.search_card = CollapsibleCard(self.control_scroll, "搜索区域")
        self.search_card.pack(fill="x", pady=5, padx=5)

        make_button(
            self.search_card.content, "选择搜索区域", self.load_search_image, "primary", icon="open"
        ).pack(fill="x", pady=3, padx=5)
        self.search_label = ctk.CTkLabel(
            self.search_card.content,
            text="未选择文件",
            wraplength=250,
            text_color=THEME["text_secondary"],
            font=FONT_SMALL,
        )
        self.search_label.pack(fill="x", pady=5, padx=5)

        # 3. 参数设置卡片
        self.param_card = CollapsibleCard(self.control_scroll, "参数设置")
        self.param_card.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(self.param_card.content, text="匹配阈值", font=FONT_NORMAL).pack(
            anchor="w", pady=(5, 2), padx=5
        )
        self.match_threshold = ctk.DoubleVar(
            value=float(self._defaults.get("match_threshold", DEFAULT_MATCH_THRESHOLD))
        )
        threshold_scale = ctk.CTkSlider(
            self.param_card.content,
            from_=0.0,
            to=1.0,
            variable=self.match_threshold,
            command=self._update_threshold,
        )
        threshold_scale.pack(fill="x", pady=2, padx=5)
        self.threshold_label = ctk.CTkLabel(
            self.param_card.content,
            text=f"当前值: {self.match_threshold.get():.2f}",
            font=FONT_SMALL,
        )
        self.threshold_label.pack(anchor="w", padx=5)

        ctk.CTkLabel(self.param_card.content, text="非极大值抑制阈值", font=FONT_NORMAL).pack(
            anchor="w", pady=(5, 2), padx=5
        )
        self.nms_threshold = ctk.DoubleVar(
            value=float(self._defaults.get("nms_radius", DEFAULT_NMS_RADIUS)) / 10
        )
        nms_scale = ctk.CTkSlider(
            self.param_card.content,
            from_=0.0,
            to=1.0,
            variable=self.nms_threshold,
            command=self._update_nms,
        )
        nms_scale.pack(fill="x", pady=2, padx=5)
        self.nms_label = ctk.CTkLabel(
            self.param_card.content, text=f"当前值: {self.nms_threshold.get():.2f}", font=FONT_SMALL
        )
        self.nms_label.pack(anchor="w", padx=5)

        # 4. 操作卡片
        self.operation_card = CollapsibleCard(self.control_scroll, "操作")
        self.operation_card.pack(fill="x", pady=5, padx=5)

        self.btn_single = ctk.CTkButton(
            self.operation_card.content,
            text="单目标匹配(找最相似)",
            state=ctk.DISABLED,
            command=self.run_single_matching,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
        )
        self.btn_single.pack(fill="x", pady=3, padx=5)

        self.btn_multi = ctk.CTkButton(
            self.operation_card.content,
            text="单目标多匹配(找所有相似)",
            state=ctk.DISABLED,
            command=self.run_single_multi_matching,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
        )
        self.btn_multi.pack(fill="x", pady=3, padx=5)

        self.btn_targets = ctk.CTkButton(
            self.operation_card.content,
            text="多目标匹配(各找一个)",
            state=ctk.DISABLED,
            command=self.run_multi_target_matching,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
        )
        self.btn_targets.pack(fill="x", pady=3, padx=5)

        self.btn_save = ctk.CTkButton(
            self.operation_card.content,
            text="保存结果",
            state=ctk.DISABLED,
            command=self.save_result,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
        )
        self.btn_save.pack(fill="x", pady=3, padx=5)

        make_button(self.operation_card.content, "清空所有", self.clear_all, "danger").pack(
            fill="x", pady=3, padx=5
        )

        # 5. 结果统计卡片
        self.result_card = CollapsibleCard(self.control_scroll, "匹配结果统计")
        self.result_card.pack(fill="x", pady=5, padx=5)

        self.template_count_label = ctk.CTkLabel(
            self.result_card.content, text="模板数量：0", font=FONT_SMALL
        )
        self.template_count_label.pack(anchor="w", pady=2, padx=5)
        self.match_count_label = ctk.CTkLabel(
            self.result_card.content, text="匹配成功：0", font=FONT_SMALL
        )
        self.match_count_label.pack(anchor="w", pady=2, padx=5)

    def build_display(self):
        """2x2 布局：3 RasterViewer + 1 matplotlib 热力图"""
        # 坐标栏
        self.coord_var = ctk.StringVar(value="")
        coord_bar = ctk.CTkFrame(self.image_frame, height=22, fg_color=THEME["statusbar"])
        coord_bar.pack(fill="x", side="top")
        ctk.CTkLabel(
            coord_bar,
            textvariable=self.coord_var,
            font=("Consolas", 9),
            text_color=THEME["text_secondary"],
        ).pack(side="left", padx=8)

        grid = ctk.CTkFrame(self.image_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        for i in range(2):
            grid.grid_rowconfigure(i, weight=1)
            grid.grid_columnconfigure(i, weight=1)

        # 左上：模板
        f1 = ctk.CTkFrame(grid, fg_color=THEME["card"])
        f1.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        ctk.CTkLabel(
            f1, text=" 模板", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_template = RasterViewer(f1)
        self.viewer_template.pack(fill="both", expand=True)

        # 右上：搜索区
        f2 = ctk.CTkFrame(grid, fg_color=THEME["card"])
        f2.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        ctk.CTkLabel(
            f2, text=" 搜索区域", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_search = RasterViewer(f2)
        self.viewer_search.pack(fill="both", expand=True)

        # 左下：匹配结果
        f3 = ctk.CTkFrame(grid, fg_color=THEME["card"])
        f3.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        ctk.CTkLabel(
            f3, text=" 匹配结果", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_result = RasterViewer(f3)
        self.viewer_result.pack(fill="both", expand=True)

        # 右下：热力图 (matplotlib)
        f4 = ctk.CTkFrame(grid, fg_color=THEME["card"])
        f4.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
        ctk.CTkLabel(
            f4,
            text=" 相关系数热力图",
            font=("Microsoft YaHei UI", 10),
            text_color=THEME["text_muted"],
        ).pack(anchor="w", padx=4, pady=1)
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        self.fig_heat = Figure(figsize=(4, 3), dpi=100, facecolor=THEME["card"])
        self.ax_heat = self.fig_heat.add_subplot(111)
        self.canvas_heat = FigureCanvasTkAgg(self.fig_heat, master=f4)
        self.canvas_heat.get_tk_widget().pack(fill="both", expand=True)

        self.viewer_template._on_coord_change = lambda t: self.coord_var.set(t)
        self.viewer_search._on_coord_change = lambda t: self.coord_var.set(t)
        self.viewer_result._on_coord_change = lambda t: self.coord_var.set(t)

    def _update_threshold(self, v):
        self.threshold_label.configure(text=f"当前值: {float(v):.2f}")

    def _update_nms(self, v):
        self.nms_label.configure(text=f"当前值: {float(v):.2f}")

    def _check_buttons(self):
        enable = len(self.templates) > 0 and self.search_img is not None
        self.btn_single.configure(state=ctk.NORMAL if enable else ctk.DISABLED)
        self.btn_multi.configure(state=ctk.NORMAL if enable else ctk.DISABLED)
        self.btn_targets.configure(state=ctk.NORMAL if enable else ctk.DISABLED)
        self.template_count_label.configure(text=f"模板数量：{len(self.templates)}")

    def _refresh_template_tree(self):
        for item in self.template_tree.get_children():
            self.template_tree.delete(item)
        for idx, (img, name, _color) in enumerate(self.templates):
            h, w = img.shape[:2]
            self.template_tree.insert("", "end", iid=str(idx), values=(name, f"{w}×{h}"))

    def _update_display(self):
        """更新所有视图"""
        if self.templates:
            sel = self.template_tree.selection()
            idx = int(sel[0]) if sel else 0
            idx = max(0, min(idx, len(self.templates) - 1))
            img, _, _ = self.templates[idx]
            geo_transform = (
                self.template_geo_transforms[idx]
                if idx < len(self.template_geo_transforms)
                else None
            )
            self.viewer_template.load(
                image_array=cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                geo_transform=geo_transform,
            )
        if self.search_img is not None:
            self.viewer_search.load(
                image_array=cv2.cvtColor(self.search_img, cv2.COLOR_BGR2RGB),
                geo_transform=self.search_geo_transform,
            )
        if self.result_img is not None:
            self.viewer_result.load(
                image_array=cv2.cvtColor(self.result_img, cv2.COLOR_BGR2RGB),
                geo_transform=self.search_geo_transform,
            )
        if self.correlation_map is not None:
            self.ax_heat.clear()
            im = self.ax_heat.imshow(self.correlation_map, cmap="jet", vmin=0, vmax=1)
            self.fig_heat.colorbar(im, ax=self.ax_heat, fraction=0.046)
            self.canvas_heat.draw()

    def add_template(self):
        paths = filedialog.askopenfilenames(filetypes=[("图像", "*.png;*.jpg;*.bmp;*.tiff")])
        if not paths:
            return
        for p in paths:
            try:
                img = self.core.load_image_with_chinese_path(p)
                name = os.path.basename(p)
                color = self.colors[len(self.templates) % len(self.colors)]
                self.templates.append((img, name, color))
                self.template_paths.append(p)
                self.template_geo_transforms.append(raster_geo_transform(p))
                record_data_source(self, p, "raster")
            except Exception as e:
                messagebox.showerror("错误", f"加载模板失败：{str(e)}")
        self._refresh_template_tree()
        self._check_buttons()
        self._update_display()
        if paths:
            mark_project_dirty(self)
            notify(self, f"已添加 {len(paths)} 个模板", "success")

    def remove_selected_template(self):
        try:
            sel = self.template_tree.selection()
            if not sel:
                raise ValueError("no selection")
            idx = int(sel[0])
            del self.templates[idx]
            del self.template_paths[idx]
            if idx < len(self.template_geo_transforms):
                del self.template_geo_transforms[idx]
            self._refresh_template_tree()
            notify(self, "模板已删除", "success")
        except Exception:
            messagebox.showwarning("提示", "请选择要删除的目标")
        self._check_buttons()
        self._update_display()

    def clear_all_templates(self):
        self.templates.clear()
        self.template_paths.clear()
        self.template_geo_transforms.clear()
        self._refresh_template_tree()
        self._check_buttons()
        self._update_display()
        notify(self, "模板已清空", "success")

    def load_search_image(self):
        p = filedialog.askopenfilename(filetypes=[("图像", "*.png;*.jpg;*.bmp;*.tiff")])
        if not p:
            return
        try:
            self.search_path = p
            self.search_img = self.core.load_image_with_chinese_path(p)
            source = record_data_source(self, p, "raster")
            self.search_geo_transform = (source or {}).get("transform") or raster_geo_transform(p)
            self.search_label.configure(text=os.path.basename(p))
            self._update_image_metadata(p)
            self._check_buttons()
            self._update_display()
            mark_project_dirty(self)
            notify(self, f"搜索区域加载完成：{os.path.basename(p)}", "success")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败：{str(e)}")

    # ========== 三个匹配方法（全部正确实现） ==========
    def run_single_matching(self):
        try:
            t_img, t_name, t_color = self.templates[0]
            res = self.core.single_matching(t_img, self.search_img, self.match_threshold.get())

            # 终极兼容：尝试所有可能的相关系数字段名
            max_corr = 0.0
            for field in ["max_correlation", "correlation", "score", "max_score", "value"]:
                if field in res:
                    max_corr = float(res[field])
                    break

            # 如果都找不到，从相关系数图中提取最大值
            if max_corr == 0 and "correlation_map" in res and res["correlation_map"] is not None:
                max_corr = float(np.max(res["correlation_map"]))

            # 自动判断匹配是否成功
            res["found"] = max_corr >= self.match_threshold.get()
            if "correlation_map" not in res:
                res["correlation_map"] = None

            self.result_img = self.core.draw_single_match_result(
                self.search_img, res, t_name, t_color
            )
            self.correlation_map = res["correlation_map"]

            # 更新统计信息
            self.match_count_label.configure(text=f"匹配成功：{1 if res['found'] else 0}")

            self._update_display()
            self.btn_save.configure(state=ctk.NORMAL)
            self.status_vars["algorithm"].set("单目标匹配")
            self.status_vars["features"].set(f"匹配: {1 if res['found'] else 0}")

            # 智能提示
            if max_corr > 0:
                notify(self, f"匹配完成，最大相关系数: {max_corr:.4f}", "success")
            else:
                messagebox.showwarning("提示", "匹配完成，但未检测到有效相关系数")
        except Exception as e:
            messagebox.showerror("错误", f"匹配失败：{str(e)}")

    def run_single_multi_matching(self):
        try:
            t_img, t_name, t_color = self.templates[0]
            res = self.core.single_multi_matching(
                t_img, self.search_img, self.match_threshold.get(), self.nms_threshold.get()
            )

            # 核心修复：兼容所有返回结构
            if "matches" not in res:
                res["matches"] = []
            if "correlation_map" not in res:
                res["correlation_map"] = None

            self.result_img = self.core.draw_multi_match_result(self.search_img, res, t_color)
            self.correlation_map = res["correlation_map"]

            # 更新统计信息
            match_count = int(res.get("total_count", len(res.get("boxes", res["matches"]))))
            self.match_count_label.configure(text=f"匹配成功：{match_count}")

            self._update_display()
            self.btn_save.configure(state=ctk.NORMAL)
            self.status_vars["algorithm"].set("多目标匹配")
            self.status_vars["features"].set(f"匹配: {match_count}")
            notify(self, f"找到 {match_count} 个匹配", "success")
        except Exception as e:
            messagebox.showerror("错误", f"匹配失败：{str(e)}")

    def run_multi_target_matching(self):
        try:
            self.status_vars["algorithm"].set("Matching...")
            self.update_idletasks()
            res = self.core.multi_target_matching(
                self.templates, self.search_img, self.match_threshold.get()
            )

            matches = res.get("results", []) if isinstance(res, dict) else res

            # 核心修复：兼容所有返回结构
            for r in matches:
                if "found" not in r:
                    r["found"] = (
                        r.get("status") == "success"
                        and r.get("max_val", r.get("correlation", 0)) >= self.match_threshold.get()
                    )

            self.result_img = self.core.draw_multi_target_result(self.search_img, res)
            self.correlation_map = None

            # 更新统计信息
            success_count = sum(1 for r in matches if r.get("found"))
            self.match_count_label.configure(
                text=f"匹配成功：{success_count}/{len(self.templates)}"
            )

            self._update_display()
            self.btn_save.configure(state=ctk.NORMAL)
            self.status_vars["algorithm"].set("多模板匹配")
            self.status_vars["features"].set(f"成功: {success_count}")
            notify(self, f"成功匹配 {success_count} 个目标", "success")
        except Exception as e:
            messagebox.showerror("错误", f"匹配失败：{str(e)}")

    def save_result(self):
        if self.result_img is None:
            messagebox.showwarning("提示", "没有可保存的结果")
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG图像", "*.png"), ("JPG图像", "*.jpg"), ("GeoTIFF", "*.tif")],
        )
        if p:
            try:
                if self._is_tiff(p) and self._is_tiff(self.search_path):
                    save_geotiff_like(self.search_path, self.result_img, p, color_order="BGR")
                else:
                    self.core.save_image_with_chinese_path(self.result_img, p)
                    if self._is_tiff(self.search_path) and not self._is_tiff(p):
                        notify(
                            self,
                            "Spatial reference is not preserved in PNG/JPEG exports.",
                            "warning",
                        )
                record_project_result(
                    self,
                    "match",
                    "导出影像匹配结果",
                    inputs=[self.search_path, *self.template_paths],
                    outputs=[p],
                    params={
                        "match_threshold": self.match_threshold.get(),
                        "nms_threshold": self.nms_threshold.get(),
                        "templates": len(self.template_paths),
                    },
                )
                notify(self, f"结果已保存：{p}", "success")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{str(e)}")

    @staticmethod
    def _is_tiff(path):
        return os.path.splitext(str(path))[1].lower() in (".tif", ".tiff")

    def clear_all(self):
        self.templates.clear()
        self.template_paths.clear()
        self.template_geo_transforms.clear()
        self._refresh_template_tree()
        self.search_img = None
        self.search_geo_transform = None
        self.result_img = None
        self.correlation_map = None
        self.search_label.configure(text="未选择文件")
        self.btn_save.configure(state=ctk.DISABLED)

        # 重置统计信息
        self.template_count_label.configure(text="模板数量：0")
        self.match_count_label.configure(text="匹配成功：0")

        self._check_buttons()
        self._update_display()
        self.status_vars["image_size"].set("无图像")
        self.status_vars["algorithm"].set("就绪")
        self.status_vars["features"].set("0")

    def _update_image_metadata(self, path):
        try:
            meta = get_image_metadata(path)
            self.status_vars["image_size"].set(
                f"{meta['width']}×{meta['height']} / {meta['bands']} bands / {meta['dtype']}"
            )
        except Exception:
            if self.search_img is not None:
                h, w = self.search_img.shape[:2]
                self.status_vars["image_size"].set(f"{w}×{h}")

    def destroy(self):
        """清理 matplotlib 资源"""
        import matplotlib.pyplot as plt

        fig = getattr(self, "fig_heat", None)
        if fig is not None:
            plt.close(fig)
        fig2 = getattr(self, "fig_result", None)
        if fig2 is not None:
            plt.close(fig2)
        super().destroy()

    # ========== 项目状态管理 ==========
    def get_state(self):
        """获取当前标签页状态，用于保存项目"""
        return {
            "template_paths": self.template_paths,
            "search_path": self.search_path,
            "match_threshold": self.match_threshold.get(),
            "nms_threshold": self.nms_threshold.get(),
        }

    def set_state(self, state):
        """从项目文件恢复状态"""
        if not state:
            return

        # 恢复参数
        self.match_threshold.set(state.get("match_threshold", DEFAULT_MATCH_THRESHOLD))
        self.nms_threshold.set(state.get("nms_threshold", DEFAULT_NMS_RADIUS / 10))
        self._update_threshold(self.match_threshold.get())
        self._update_nms(self.nms_threshold.get())

        # 加载搜索图像
        search_path = state.get("search_path", "")
        if search_path and os.path.exists(search_path):
            try:
                self.search_path = search_path
                self.search_img = self.core.load_image_with_chinese_path(search_path)
                self.search_geo_transform = raster_geo_transform(search_path)
                self.search_label.configure(text=os.path.basename(search_path))
                self._update_image_metadata(search_path)
            except Exception:
                pass

        # 加载模板图像
        template_paths = state.get("template_paths", [])
        self.templates = []
        self.template_paths = []
        self.template_geo_transforms = []
        self._refresh_template_tree()
        for path in template_paths:
            if os.path.exists(path):
                try:
                    img = self.core.load_image_with_chinese_path(path)
                    name = os.path.basename(path)
                    color = self.colors[len(self.templates) % len(self.colors)]
                    self.templates.append((img, name, color))
                    self.template_paths.append(path)
                    self.template_geo_transforms.append(raster_geo_transform(path))
                except Exception:
                    pass

        self._refresh_template_tree()
        self._check_buttons()
        self._update_display()
