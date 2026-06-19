# ui/feature_tab.py
import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from core.feature_detection import FeatureDetection
from data.image_io import get_image_metadata

from .raster_viewer import RasterViewer
from .settings_manager import load_settings
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard
from .ui_helpers import make_button, notify, record_project_result


class FeatureTab(ctk.CTkFrame):
    def __init__(self, parent, status_vars):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self.status_vars = status_vars
        self.detector = FeatureDetection()
        defaults = load_settings().get("defaults", {})

        # 图像变量
        self.original_img = None
        self.result_img = None
        self.image_path = ""

        # 参数变量
        self.angle = ctk.DoubleVar(value=0.0)
        self.scale_ratio = ctk.DoubleVar(value=1.0)
        self.interp_method = ctk.StringVar(value="bilinear")
        self.feature_method = ctk.StringVar(value="harris")
        self.point_size = ctk.IntVar(value=int(defaults.get("point_size", 4)))
        self.enable_feature = ctk.IntVar(value=1)
        self.harris_k = ctk.DoubleVar(value=float(defaults.get("harris_k", 0.04)))
        self.susan_t = ctk.IntVar(value=int(defaults.get("susan_t", 25)))

        # 阈值配置
        self.thresh_cfg = {
            "harris": {"min": 0.001, "max": 0.1, "step": 0.001, "default": 0.01},
            "moravec": {"min": 0.01, "max": 0.2, "step": 0.005, "default": 0.05},
            "forstner": {"min": 0.0005, "max": 0.02, "step": 0.0005, "default": 0.001},
            "susan": {"min": 0.05, "max": 0.5, "step": 0.01, "default": 0.2},
        }
        self.cur_thresh = ctk.DoubleVar(value=self.thresh_cfg["harris"]["default"])

        # 初始化UI
        self.init_ui()
        self.bind_realtime_render()

    def init_ui(self):
        # 1:3 统一布局（修复：明确设置行和列的权重）
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=280)
        self.grid_columnconfigure(1, weight=3)

        # 左侧可滚动控制面板
        self.control_scroll = ctk.CTkScrollableFrame(self, **PANEL_STYLE)
        self.control_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 右侧双窗口显示区
        self.display_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.display_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.build_control()
        self.build_display()

    def build_control(self):
        # 1. 数据管理卡片
        self.data_card = CollapsibleCard(self.control_scroll, "数据管理")
        self.data_card.pack(fill="x", pady=5, padx=5)

        make_button(
            self.data_card.content, "加载图像", self.load_image, "primary", icon="open"
        ).pack(fill="x", pady=3, padx=5)
        make_button(
            self.data_card.content, "保存结果", self.save_result, "secondary", icon="save"
        ).pack(fill="x", pady=3, padx=5)
        make_button(self.data_card.content, "重置视图", self.reset_view).pack(
            fill="x", pady=3, padx=5
        )

        # 2. 几何变换卡片
        self.geom_card = CollapsibleCard(self.control_scroll, "几何变换")
        self.geom_card.pack(fill="x", pady=5, padx=5)

        self.add_slider_entry(self.geom_card.content, "旋转角度", self.angle, -180, 180, 1)
        self.add_slider_entry(self.geom_card.content, "缩放比例", self.scale_ratio, 0.2, 2.0, 0.05)

        ctk.CTkLabel(self.geom_card.content, text="插值方法", font=FONT_NORMAL).pack(
            anchor="w", pady=(5, 2), padx=5
        )
        ctk.CTkOptionMenu(
            self.geom_card.content, variable=self.interp_method, values=["bilinear", "bicubic"]
        ).pack(fill="x", pady=2, padx=5)

        # 3. 特征检测卡片
        self.feature_card = CollapsibleCard(self.control_scroll, "特征检测")
        self.feature_card.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(self.feature_card.content, text="检测算法", font=FONT_NORMAL).pack(
            anchor="w", pady=(5, 2), padx=5
        )
        ctk.CTkOptionMenu(
            self.feature_card.content,
            variable=self.feature_method,
            values=["harris", "moravec", "forstner", "susan"],
            command=self.switch_method,
        ).pack(fill="x", pady=2, padx=5)

        # Harris参数
        self.harris_frame = ctk.CTkFrame(self.feature_card.content, fg_color="transparent")
        self.add_slider_entry(self.harris_frame, "Harris k", self.harris_k, 0.01, 0.1, 0.001)

        # SUSAN参数
        self.susan_frame = ctk.CTkFrame(self.feature_card.content, fg_color="transparent")
        self.add_slider_entry(self.susan_frame, "SUSAN T", self.susan_t, 5, 50, 1)

        # 通用阈值
        self.thresh_frame = ctk.CTkFrame(self.feature_card.content, fg_color="transparent")
        self.add_slider_entry(
            self.thresh_frame,
            "检测阈值",
            self.cur_thresh,
            self.thresh_cfg["harris"]["min"],
            self.thresh_cfg["harris"]["max"],
            self.thresh_cfg["harris"]["step"],
        )

        # 点大小
        self.add_slider_entry(self.feature_card.content, "特征点大小", self.point_size, 1, 5, 1)

        # 显示开关
        ctk.CTkCheckBox(
            self.feature_card.content,
            text="显示特征点",
            variable=self.enable_feature,
            font=FONT_NORMAL,
        ).pack(pady=5, padx=5, anchor="w")

        # 4. 结果统计卡片
        self.stat_card = CollapsibleCard(self.control_scroll, "结果统计")
        self.stat_card.pack(fill="x", pady=5, padx=5)

        self.count_label = ctk.CTkLabel(
            self.stat_card.content,
            text="检测到特征点：0",
            text_color=THEME["success"],
            font=FONT_SUBTITLE,
        )
        self.count_label.pack(pady=5, padx=5)

        # 初始化显示参数面板
        self.switch_method()

    def build_display(self):
        """双窗口布局：原图 + 结果图（RasterViewer + 坐标栏）"""
        # 坐标状态栏（顶部）
        self.coord_var = ctk.StringVar(value="")
        coord_bar = ctk.CTkFrame(self.display_frame, height=22, fg_color=THEME["statusbar"])
        coord_bar.pack(fill="x", side="top")
        ctk.CTkLabel(
            coord_bar,
            textvariable=self.coord_var,
            font=("Consolas", 9),
            text_color=THEME["text_secondary"],
        ).pack(side="left", padx=8)

        # 双 RasterViewer 并排
        top = ctk.CTkFrame(self.display_frame, fg_color="transparent")
        top.pack(fill="both", expand=True)

        left = ctk.CTkFrame(top, fg_color=THEME["card"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 1))
        ctk.CTkLabel(
            left, text=" 原始图像", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_original = RasterViewer(left)
        self.viewer_original.pack(fill="both", expand=True)

        right = ctk.CTkFrame(top, fg_color=THEME["card"])
        right.pack(side="right", fill="both", expand=True, padx=(1, 0))
        ctk.CTkLabel(
            right, text=" 检测结果", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_result = RasterViewer(right)
        self.viewer_result.pack(fill="both", expand=True)

        self.viewer_original._on_coord_change = lambda t: self.coord_var.set(t)
        self.viewer_result._on_coord_change = lambda t: self.coord_var.set(t)

    def add_slider_entry(self, parent, text, var, min_v, max_v, step):
        """滑块+输入框组合组件"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=2, padx=5)

        ctk.CTkLabel(frame, text=text, font=FONT_NORMAL).pack(side="left", padx=2)
        slider = ctk.CTkSlider(frame, from_=min_v, to=max_v, variable=var)
        slider.pack(side="left", fill="x", expand=True, padx=5)
        entry = ctk.CTkEntry(frame, width=60, font=FONT_SMALL)
        entry.insert(0, str(var.get()))
        entry.pack(side="left", padx=2)

        # 双向绑定
        def update_var(*args):
            try:
                var.set(float(entry.get()))
            except Exception:
                logger.debug("忽略非关键错误")
                pass

        entry.bind("<Return>", update_var)
        var.trace_add(
            "write", lambda *a: (entry.delete(0, "end"), entry.insert(0, f"{var.get():.3f}"))
        )

    def bind_realtime_render(self):
        """实时渲染绑定：参数变化自动重新计算"""
        vars_list = [
            self.angle,
            self.scale_ratio,
            self.interp_method,
            self.feature_method,
            self.point_size,
            self.enable_feature,
            self.harris_k,
            self.susan_t,
            self.cur_thresh,
        ]
        for v in vars_list:
            v.trace_add("write", self.render)

    def render(self, *args):
        """核心渲染函数"""
        if self.original_img is None:
            return

        # 旋转+缩放
        img = self.detector.rotate_image(
            self.original_img,
            angle=self.angle.get(),
            scale=self.scale_ratio.get(),
            interp_method=self.interp_method.get(),
        )

        # 角点检测
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        method = self.feature_method.get()

        try:
            if method == "harris":
                mask, cnt = self.detector.harris_detect(
                    gray, self.harris_k.get(), self.cur_thresh.get()
                )
            elif method == "moravec":
                mask, cnt = self.detector.moravec_detect(gray, self.cur_thresh.get())
            elif method == "forstner":
                mask, cnt = self.detector.forstner_detect(gray, self.cur_thresh.get())
            else:
                mask, cnt = self.detector.susan_detect(
                    gray, self.susan_t.get(), self.cur_thresh.get()
                )
        except Exception as e:
            messagebox.showerror("错误", f"检测失败：{str(e)}")
            return

        # 绘制特征点
        if self.enable_feature.get():
            self.result_img = self.detector.draw_points(img, mask, self.point_size.get())
        else:
            self.result_img = img

        # 更新显示（RasterViewer）
        self.viewer_original.load(image_array=cv2.cvtColor(self.original_img, cv2.COLOR_BGR2RGB))
        self.viewer_result.load(image_array=cv2.cvtColor(self.result_img, cv2.COLOR_BGR2RGB))

        # 更新统计信息和状态栏
        self.count_label.configure(text=f"检测到特征点：{cnt}")
        h, w = self.original_img.shape[:2]
        self.status_vars["image_size"].set(f"{w}×{h}")
        self.status_vars["algorithm"].set(method.upper())
        self.status_vars["features"].set(f"{cnt} 个")

    def load_image(self):
        """加载图像"""
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png;*.jpg;*.bmp;*.tiff")])
        if path:
            try:
                self.image_path = path
                self.original_img = self.detector.load_image(path)
                self.render()
                self._update_image_metadata(path)
                notify(self, f"图像加载完成：{os.path.basename(path)}", "success")
            except Exception as e:
                messagebox.showerror("错误", f"加载失败：{str(e)}")

    def load_image_silent(self, path):
        """从拖拽等外部入口加载图像。"""
        self.image_path = path
        self.original_img = self.detector.load_image(path)
        self.render()
        self._update_image_metadata(path)
        notify(self, f"图像加载完成：{os.path.basename(path)}", "success")

    def save_result(self):
        """保存结果图像"""
        if self.result_img is None:
            messagebox.showwarning("提示", "请先加载图像并执行检测")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG图像", "*.png"), ("JPG图像", "*.jpg")]
        )
        if path:
            try:
                self.detector.save_image(self.result_img, path)
                record_project_result(
                    self,
                    "feature",
                    "导出特征检测结果",
                    inputs=[self.image_path],
                    outputs=[path],
                    params={
                        "method": self.feature_method.get(),
                        "threshold": self.cur_thresh.get(),
                        "harris_k": self.harris_k.get(),
                        "susan_t": self.susan_t.get(),
                        "point_size": self.point_size.get(),
                    },
                )
                notify(self, f"结果已保存：{path}", "success")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{str(e)}")

    def reset_view(self):
        """重置视图参数"""
        self.angle.set(0)
        self.scale_ratio.set(1)
        self.render()

    def _update_image_metadata(self, path):
        try:
            meta = get_image_metadata(path)
            self.status_vars["image_size"].set(
                f"{meta['width']}×{meta['height']} / {meta['bands']} bands / {meta['dtype']}"
            )
        except Exception:
            pass

    def switch_method(self, *args):
        """切换检测算法，自动切换参数面板"""
        meth = self.feature_method.get()
        cfg = self.thresh_cfg[meth]
        self.cur_thresh.set(cfg["default"])

        # 切换参数面板
        for widget in [self.harris_frame, self.susan_frame, self.thresh_frame]:
            widget.pack_forget()

        if meth == "harris":
            self.harris_frame.pack(fill="x", pady=2, padx=5)
        elif meth == "susan":
            self.susan_frame.pack(fill="x", pady=2, padx=5)

        self.thresh_frame.pack(fill="x", pady=2, padx=5)

    # ========== 项目状态管理 ==========
    def get_state(self):
        """获取当前标签页状态，用于保存项目"""
        return {
            "image_path": self.image_path,
            "angle": self.angle.get(),
            "scale_ratio": self.scale_ratio.get(),
            "interp_method": self.interp_method.get(),
            "feature_method": self.feature_method.get(),
            "point_size": self.point_size.get(),
            "enable_feature": self.enable_feature.get(),
            "harris_k": self.harris_k.get(),
            "susan_t": self.susan_t.get(),
            "threshold": self.cur_thresh.get(),
        }

    def set_state(self, state):
        """从项目文件恢复状态"""
        if not state:
            return

        # 恢复参数
        self.angle.set(state.get("angle", 0.0))
        self.scale_ratio.set(state.get("scale_ratio", 1.0))
        self.interp_method.set(state.get("interp_method", "bilinear"))
        self.feature_method.set(state.get("feature_method", "harris"))
        self.point_size.set(state.get("point_size", 4))
        self.enable_feature.set(state.get("enable_feature", 1))
        self.harris_k.set(state.get("harris_k", 0.04))
        self.susan_t.set(state.get("susan_t", 25))
        self.cur_thresh.set(state.get("threshold", 0.01))

        # 切换算法参数面板
        self.switch_method()

        # 加载图像
        image_path = state.get("image_path", "")
        if image_path and os.path.exists(image_path):
            try:
                self.image_path = image_path
                self.original_img = self.detector.load_image(image_path)
                self.render()
            except Exception:
                pass

    def destroy(self):
        """销毁时清理资源"""
        fig = getattr(self, "fig", None)
        if fig is not None:
            plt.close(fig)
        super().destroy()
