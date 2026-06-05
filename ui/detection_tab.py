from common import utils
"""ONNX 目标检测面板"""
import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

from core.detection import ONNXDetector, DetectionOutput
from .theme import THEME, FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, SECTION_STYLE


class DetectionTab(ctk.CTkFrame):
    """深度学习目标检测面板"""

    def __init__(self, parent, status_vars=None):
        super().__init__(parent, fg_color=THEME["bg"])
        self.status_vars = status_vars or {}
        self.detector = ONNXDetector(confidence=0.5, iou_threshold=0.45)
        self.current_image = None
        self.result_image = None
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 左侧控制面板
        side = ctk.CTkFrame(self, width=280, fg_color=THEME["panel"])
        side.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="目标检测", font=("Microsoft YaHei UI", 16, "bold")
                    ).pack(anchor="w", padx=14, pady=(14, 8))

        if not self.detector.available:
            ctk.CTkLabel(side, text="⚠ 未加载模型", font=FONT_SMALL,
                        text_color=THEME["warning"]).pack(anchor="w", padx=14, pady=4)

        # 模型选择
        ctk.CTkLabel(side, text="ONNX 模型", font=FONT_SMALL).pack(anchor="w", padx=14, pady=(10, 2))
        model_row = ctk.CTkFrame(side, fg_color="transparent")
        model_row.pack(fill="x", padx=14)
        self.model_path_var = ctk.StringVar(value="未选择模型")
        self.model_label = ctk.CTkLabel(model_row, textvariable=self.model_path_var,
                                        font=("Consolas", 9), text_color=THEME["text_muted"])
        self.model_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(model_row, text="...", command=self._load_model,
                     width=30, height=24, font=FONT_SMALL).pack(side="right")

        # 参数控制
        ctk.CTkLabel(side, text="置信度阈值", font=FONT_SMALL).pack(anchor="w", padx=14, pady=(10, 2))
        self.conf_slider = ctk.CTkSlider(side, from_=0.1, to=1.0, number_of_steps=18,
                                         command=self._on_conf_change)
        self.conf_slider.pack(fill="x", padx=14)
        self.conf_slider.set(0.5)
        self.conf_label = ctk.CTkLabel(side, text="0.50", font=FONT_SMALL, text_color=THEME["text_muted"])
        self.conf_label.pack(anchor="w", padx=14)

        ctk.CTkLabel(side, text="IOU 阈值", font=FONT_SMALL).pack(anchor="w", padx=14, pady=(8, 2))
        self.iou_slider = ctk.CTkSlider(side, from_=0.1, to=1.0, number_of_steps=18,
                                        command=self._on_iou_change)
        self.iou_slider.pack(fill="x", padx=14)
        self.iou_slider.set(0.45)
        self.iou_label = ctk.CTkLabel(side, text="0.45", font=FONT_SMALL, text_color=THEME["text_muted"])
        self.iou_label.pack(anchor="w", padx=14)

        # 按钮
        ctk.CTkButton(side, text="打开影像", command=self._open_image,
                     fg_color=THEME["accent"], height=32, font=FONT_NORMAL,
                     corner_radius=6).pack(fill="x", padx=14, pady=(16, 4))

        ctk.CTkButton(side, text="执行检测", command=self._run_detection,
                     fg_color=THEME["success"], height=32, font=FONT_NORMAL,
                     corner_radius=6).pack(fill="x", padx=14, pady=(4, 4))

        ctk.CTkButton(side, text="导出结果", command=self._export_result,
                     fg_color="transparent", border_width=1, border_color=THEME["border"],
                     text_color=THEME["text_primary"], height=30, font=FONT_SMALL,
                     corner_radius=6).pack(fill="x", padx=14, pady=(4, 10))

        # 状态
        self.detect_status = ctk.CTkLabel(side, text="就绪", font=FONT_SMALL,
                                         text_color=THEME["text_secondary"])
        self.detect_status.pack(anchor="w", padx=14, pady=(4, 10))

        # 右侧影像显示
        self.image_frame = ctk.CTkFrame(self, fg_color=THEME["card"])
        self.image_frame.grid(row=0, column=1, sticky="nsew")
        self.image_label = ctk.CTkLabel(self.image_frame, text="拖入影像或点击「打开影像」",
                                       font=FONT_NORMAL, text_color=THEME["text_muted"])
        self.image_label.place(relx=0.5, rely=0.5, anchor="center")

    def _on_conf_change(self, val):
        self.conf_label.configure(text=f"{float(val):.2f}")
        self.detector.confidence = float(val)

    def _on_iou_change(self, val):
        self.iou_label.configure(text=f"{float(val):.2f}")
        self.detector.iou_threshold = float(val)

    def _load_model(self):
        path = filedialog.askopenfilename(
            title="选择 ONNX 模型", filetypes=[("ONNX 模型", "*.onnx"), ("所有文件", "*.*")]
        )
        if path:
            if self.detector.load_model(path):
                name = os.path.basename(path)
                self.model_path_var.set(name)
                self.detect_status.configure(text="模型已加载", text_color=THEME["success"])
            else:
                messagebox.showerror("错误", "模型加载失败")

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="打开影像",
            filetypes=[("影像文件", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp")]
        )
        if path:
            self.current_image = utils.imread_chinese(path)
            if self.current_image is not None:
                self._show_image(self.current_image)
                self.detect_status.configure(text=f"已加载: {os.path.basename(path)}",
                                            text_color=THEME["text_secondary"])
                if self.status_vars.get("image_size"):
                    h, w = self.current_image.shape[:2]
                    self.status_vars["image_size"].set(f"{w}x{h}")

    def _run_detection(self):
        if not self.detector.available:
            messagebox.showwarning("提示", "请先加载 ONNX 模型")
            return
        if self.current_image is None:
            messagebox.showwarning("提示", "请先打开影像")
            return
        self.detect_status.configure(text="正在检测...", text_color=THEME["warning"])
        self.update_idletasks()

        output = self.detector.detect(self.current_image)
        self.result_image = self.detector.draw_detections(self.current_image, output)
        self._show_image(self.result_image)

        self.detect_status.configure(
            text=f"检测到 {output.count} 个目标 ({output.inference_time_ms:.0f}ms)",
            text_color=THEME["success"]
        )
        if self.status_vars.get("features"):
            self.status_vars["features"].set(str(output.count))

    def _export_result(self):
        if self.result_image is None:
            messagebox.showwarning("提示", "请先执行检测")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")]
        )
        if path:
            utils.imwrite_chinese(path, self.result_image)
            messagebox.showinfo("成功", f"结果已保存至 {path}")

    def _show_image(self, img):
        h, w = img.shape[:2]
        fw = self.image_frame.winfo_width() or 800
        fh = self.image_frame.winfo_height() or 600
        scale = min(fw / w, fh / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        if nw < 10 or nh < 10:
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(nw, nh))
        self.image_label.configure(image=ctk_img, text="")
        self.image_label._image = ctk_img
