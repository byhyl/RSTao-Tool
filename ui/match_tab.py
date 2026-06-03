# ui/match_tab.py
import os
import warnings
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from core import ImageMatchingCore

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard

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
        self.search_path = ""
        self.search_img = None
        self.result_img = None
        self.correlation_map = None
        self.colors = self.core.colors

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

        ctk.CTkButton(
            self.template_card.content, text="添加目标窗口", command=self.add_template
        ).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(
            self.template_card.content, text="删除选中目标", command=self.remove_selected_template
        ).pack(fill="x", pady=3, padx=5)
        ctk.CTkButton(
            self.template_card.content, text="清空所有目标", command=self.clear_all_templates
        ).pack(fill="x", pady=3, padx=5)

        self.template_listbox = ctk.CTkTextbox(
            self.template_card.content, height=4, font=FONT_SMALL
        )
        self.template_listbox.pack(fill="x", pady=5, padx=5)

        # 2. 搜索区域卡片
        self.search_card = CollapsibleCard(self.control_scroll, "搜索区域")
        self.search_card.pack(fill="x", pady=5, padx=5)

        ctk.CTkButton(
            self.search_card.content, text="选择搜索区域", command=self.load_search_image
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
        self.match_threshold = ctk.DoubleVar(value=DEFAULT_MATCH_THRESHOLD)
        threshold_scale = ctk.CTkSlider(
            self.param_card.content,
            from_=0.0,
            to=1.0,
            variable=self.match_threshold,
            command=self._update_threshold,
        )
        threshold_scale.pack(fill="x", pady=2, padx=5)
        self.threshold_label = ctk.CTkLabel(
            self.param_card.content, text=f"当前值: {DEFAULT_MATCH_THRESHOLD:.2f}", font=FONT_SMALL
        )
        self.threshold_label.pack(anchor="w", padx=5)

        ctk.CTkLabel(self.param_card.content, text="非极大值抑制阈值", font=FONT_NORMAL).pack(
            anchor="w", pady=(5, 2), padx=5
        )
        self.nms_threshold = ctk.DoubleVar(value=DEFAULT_NMS_RADIUS / 10)
        nms_scale = ctk.CTkSlider(
            self.param_card.content,
            from_=0.0,
            to=1.0,
            variable=self.nms_threshold,
            command=self._update_nms,
        )
        nms_scale.pack(fill="x", pady=2, padx=5)
        self.nms_label = ctk.CTkLabel(
            self.param_card.content, text=f"当前值: {DEFAULT_NMS_RADIUS/10:.2f}", font=FONT_SMALL
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
        )
        self.btn_single.pack(fill="x", pady=3, padx=5)

        self.btn_multi = ctk.CTkButton(
            self.operation_card.content,
            text="单目标多匹配(找所有相似)",
            state=ctk.DISABLED,
            command=self.run_single_multi_matching,
        )
        self.btn_multi.pack(fill="x", pady=3, padx=5)

        self.btn_targets = ctk.CTkButton(
            self.operation_card.content,
            text="多目标匹配(各找一个)",
            state=ctk.DISABLED,
            command=self.run_multi_target_matching,
        )
        self.btn_targets.pack(fill="x", pady=3, padx=5)

        self.btn_save = ctk.CTkButton(
            self.operation_card.content,
            text="保存结果",
            state=ctk.DISABLED,
            command=self.save_result,
        )
        self.btn_save.pack(fill="x", pady=3, padx=5)

        ctk.CTkButton(self.operation_card.content, text="清空所有", command=self.clear_all).pack(
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
        # 2x2 图像显示布局
        self.fig = Figure(figsize=(12, 8), dpi=100, facecolor=THEME["panel"])
        gs = self.fig.add_gridspec(2, 2, wspace=0.1, hspace=0.15)

        self.ax1 = self.fig.add_subplot(gs[0, 0])
        self.ax2 = self.fig.add_subplot(gs[0, 1])
        self.ax3 = self.fig.add_subplot(gs[1, 0])
        self.ax4 = self.fig.add_subplot(gs[1, 1])

        for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
            ax.axis("off")
            ax.set_facecolor(THEME["panel"])
        self.ax1.set_title("目标窗口预览", fontsize=10, color=THEME["text_primary"])
        self.ax2.set_title("搜索区域", fontsize=10, color=THEME["text_primary"])
        self.ax3.set_title("匹配结果", fontsize=10, color=THEME["text_primary"])
        self.ax4.set_title("相关系数热力图", fontsize=10, color=THEME["text_primary"])

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.image_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.image_frame)
        self.toolbar.config(background=THEME["panel"])
        self.toolbar.update()

        self.fig.canvas.draw()

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

    def _update_display(self):
        for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
            ax.clear()
            ax.axis("off")
            ax.set_facecolor(THEME["panel"])
        self.ax1.set_title("目标窗口预览", fontsize=10, color=THEME["text_primary"])
        self.ax2.set_title("搜索区域", fontsize=10, color=THEME["text_primary"])
        self.ax3.set_title("匹配结果", fontsize=10, color=THEME["text_primary"])
        self.ax4.set_title("相关系数热力图", fontsize=10, color=THEME["text_primary"])

        if self.templates:
            img, name, _ = self.templates[0]
            self.ax1.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if self.search_img is not None:
            self.ax2.imshow(cv2.cvtColor(self.search_img, cv2.COLOR_BGR2RGB))
        if self.result_img is not None:
            self.ax3.imshow(cv2.cvtColor(self.result_img, cv2.COLOR_BGR2RGB))
        if self.correlation_map is not None:
            im = self.ax4.imshow(self.correlation_map, cmap="jet", vmin=0, vmax=1)
            self.fig.colorbar(im, ax=self.ax4, shrink=0.8)

        self.canvas.draw()

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
                self.template_listbox.insert(ctk.END, name + "\n")
            except Exception as e:
                messagebox.showerror("错误", f"加载模板失败：{str(e)}")
        self._check_buttons()
        self._update_display()

    def remove_selected_template(self):
        try:
            idx = self.template_listbox.index("sel.first")
            idx = int(idx.split(".")[0]) - 1
            del self.templates[idx]
            del self.template_paths[idx]
            self.template_listbox.delete(1.0, ctk.END)
            for _, n, _ in self.templates:
                self.template_listbox.insert(ctk.END, n + "\n")
        except Exception:
            messagebox.showwarning("提示", "请选择要删除的目标")
        self._check_buttons()
        self._update_display()

    def clear_all_templates(self):
        self.templates.clear()
        self.template_paths.clear()
        self.template_listbox.delete(1.0, ctk.END)
        self._check_buttons()
        self._update_display()

    def load_search_image(self):
        p = filedialog.askopenfilename(filetypes=[("图像", "*.png;*.jpg;*.bmp;*.tiff")])
        if not p:
            return
        try:
            self.search_path = p
            self.search_img = self.core.load_image_with_chinese_path(p)
            self.search_label.configure(text=os.path.basename(p))
            h, w = self.search_img.shape[:2]
            self.status_vars["image_size"].set(f"{w}×{h}")
            self._check_buttons()
            self._update_display()
            messagebox.showinfo("成功", "搜索区域加载完成")
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
                messagebox.showinfo("成功", f"匹配完成，最大相关系数: {max_corr:.4f}")
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
            match_count = len(res["matches"])
            self.match_count_label.configure(text=f"匹配成功：{match_count}")

            self._update_display()
            self.btn_save.configure(state=ctk.NORMAL)
            self.status_vars["algorithm"].set("多目标匹配")
            self.status_vars["features"].set(f"匹配: {match_count}")
            messagebox.showinfo("成功", f"找到 {match_count} 个匹配")
        except Exception as e:
            messagebox.showerror("错误", f"匹配失败：{str(e)}")

    def run_multi_target_matching(self):
        try:
            res = self.core.multi_target_matching(
                self.templates, self.search_img, self.match_threshold.get()
            )

            # 核心修复：兼容所有返回结构
            for r in res:
                if "found" not in r:
                    r["found"] = r.get("correlation", 0) >= self.match_threshold.get()

            self.result_img = self.core.draw_multi_target_result(self.search_img, res)
            self.correlation_map = None

            # 更新统计信息
            success_count = sum(1 for r in res if r["found"])
            self.match_count_label.configure(
                text=f"匹配成功：{success_count}/{len(self.templates)}"
            )

            self._update_display()
            self.btn_save.configure(state=ctk.NORMAL)
            self.status_vars["algorithm"].set("多模板匹配")
            self.status_vars["features"].set(f"成功: {success_count}")
            messagebox.showinfo("成功", f"成功匹配 {success_count} 个目标")
        except Exception as e:
            messagebox.showerror("错误", f"匹配失败：{str(e)}")

    def save_result(self):
        if self.result_img is None:
            messagebox.showwarning("提示", "没有可保存的结果")
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG图像", "*.png"), ("JPG图像", "*.jpg")]
        )
        if p:
            try:
                self.core.save_image_with_chinese_path(self.result_img, p)
                messagebox.showinfo("成功", "保存完成")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{str(e)}")

    def clear_all(self):
        self.templates.clear()
        self.template_paths.clear()
        self.template_listbox.delete(1.0, ctk.END)
        self.search_img = None
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
                self.search_label.configure(text=os.path.basename(search_path))
            except:
                pass

        # 加载模板图像
        template_paths = state.get("template_paths", [])
        self.templates = []
        self.template_paths = []
        self.template_listbox.delete(1.0, ctk.END)
        for path in template_paths:
            if os.path.exists(path):
                try:
                    img = self.core.load_image_with_chinese_path(path)
                    name = os.path.basename(path)
                    color = self.colors[len(self.templates) % len(self.colors)]
                    self.templates.append((img, name, color))
                    self.template_paths.append(path)
                    self.template_listbox.insert(ctk.END, name + "\n")
                except:
                    pass

        self._check_buttons()
        self._update_display()
