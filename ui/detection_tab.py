from common import utils

"""ONNX 目标检测面板"""
import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

from core.detection import DetectionOutput, ONNXDetector
from core.model_registry import ModelConfig, ModelRegistry, infer_model_config
from data.image_io import get_image_metadata, save_geotiff_like

from .error_dialog import show_actionable_error
from .import_preview_dialog import confirm_import
from .raster_viewer import RasterViewer
from .settings_manager import load_settings
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, SECTION_STYLE, THEME
from .ui_helpers import (
    make_button,
    mark_project_dirty,
    notify,
    raster_geo_transform,
    record_data_source,
    record_project_result,
    run_background,
)


class DetectionTab(ctk.CTkFrame):
    """深度学习目标检测面板"""

    def __init__(self, parent, status_vars=None):
        super().__init__(parent, fg_color=THEME["bg"])
        self.status_vars = status_vars or {}
        defaults = load_settings().get("defaults", {})
        self.detector = ONNXDetector(
            confidence=float(defaults.get("confidence", 0.5)),
            iou_threshold=float(defaults.get("iou_threshold", 0.45)),
        )
        self.model_registry = ModelRegistry()
        self.model_config = None
        self.current_image = None
        self.current_image_path = ""
        self.current_geo_transform = None
        self.result_image = None
        self.last_output = None
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 左侧控制面板
        side = ctk.CTkFrame(self, width=300, fg_color=THEME["panel"])
        side.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="目标检测", font=("Microsoft YaHei UI", 16, "bold")).pack(
            anchor="w", padx=14, pady=(14, 8)
        )

        if not self.detector.available:
            ctk.CTkLabel(
                side, text="⚠ 未加载模型", font=FONT_SMALL, text_color=THEME["warning"]
            ).pack(anchor="w", padx=14, pady=4)

        # 模型选择
        ctk.CTkLabel(side, text="ONNX 模型", font=FONT_SMALL).pack(
            anchor="w", padx=14, pady=(10, 2)
        )
        model_row = ctk.CTkFrame(side, fg_color="transparent")
        model_row.pack(fill="x", padx=14)
        self.model_path_var = ctk.StringVar(value="未选择模型")
        self.model_label = ctk.CTkLabel(
            model_row,
            textvariable=self.model_path_var,
            font=("Consolas", 9),
            text_color=THEME["text_muted"],
        )
        self.model_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            model_row, text="...", command=self._load_model, width=30, height=24, font=FONT_SMALL
        ).pack(side="right")

        # 参数控制
        ctk.CTkLabel(side, text="置信度阈值", font=FONT_SMALL).pack(
            anchor="w", padx=14, pady=(10, 2)
        )
        self.conf_slider = ctk.CTkSlider(
            side, from_=0.1, to=1.0, number_of_steps=18, command=self._on_conf_change
        )
        self.conf_slider.pack(fill="x", padx=14)
        self.conf_slider.set(self.detector.confidence)
        self.conf_label = ctk.CTkLabel(
            side,
            text=f"{self.detector.confidence:.2f}",
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
        )
        self.conf_label.pack(anchor="w", padx=14)

        ctk.CTkLabel(side, text="IOU 阈值", font=FONT_SMALL).pack(anchor="w", padx=14, pady=(8, 2))
        self.iou_slider = ctk.CTkSlider(
            side, from_=0.1, to=1.0, number_of_steps=18, command=self._on_iou_change
        )
        self.iou_slider.pack(fill="x", padx=14)
        self.iou_slider.set(self.detector.iou_threshold)
        self.iou_label = ctk.CTkLabel(
            side,
            text=f"{self.detector.iou_threshold:.2f}",
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
        )
        self.iou_label.pack(anchor="w", padx=14)

        # 按钮
        make_button(side, "打开影像", self._open_image, "primary", icon="open").pack(
            fill="x", padx=14, pady=(16, 4)
        )

        self.btn_detect = make_button(side, "执行检测", self._run_detection, "success")
        self.btn_detect.pack(fill="x", padx=14, pady=(4, 4))

        make_button(
            side, "导出结果", self._export_result, "secondary", icon="export", height=30
        ).pack(fill="x", padx=14, pady=(4, 10))

        # 状态
        self.detect_status = ctk.CTkLabel(
            side, text="就绪", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        self.detect_status.pack(anchor="w", padx=14, pady=(4, 10))

        # 右侧影像显示
        self.image_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.image_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        self.viewer = RasterViewer(self.image_frame)
        self.viewer.pack(fill="both", expand=True)

    def _on_conf_change(self, val):
        self.conf_label.configure(text=f"{float(val):.2f}")
        self.detector.confidence = float(val)
        self._sync_model_config()

    def _on_iou_change(self, val):
        self.iou_label.configure(text=f"{float(val):.2f}")
        self.detector.iou_threshold = float(val)
        self._sync_model_config()

    def _sync_model_config(self):
        if not self.model_config:
            return
        self.model_config.confidence = float(self.detector.confidence)
        self.model_config.iou_threshold = float(self.detector.iou_threshold)
        self.detector.model_config = self.model_config.to_dict()
        self.model_registry.save(self.model_config)

    def _load_model(self):
        path = filedialog.askopenfilename(
            title="选择 ONNX 模型", filetypes=[("ONNX 模型", "*.onnx"), ("所有文件", "*.*")]
        )
        if path:
            try:
                if not confirm_import(self, path, "onnx"):
                    return
                if self.detector.load_model(path):
                    self._apply_model_config(path)
                    name = os.path.basename(path)
                    self.model_path_var.set(name)
                    self.detect_status.configure(text="模型已加载", text_color=THEME["success"])
                    mark_project_dirty(self)
                else:
                    show_actionable_error(
                        self,
                        "模型加载失败",
                        "ONNX 模型没有成功加载。",
                        "请确认模型格式兼容 ONNX Runtime，并检查输入输出形状。",
                    )
            except Exception as exc:
                show_actionable_error(
                    self,
                    "模型加载失败",
                    "ONNX 模型预检或加载时发生异常。",
                    "请确认模型文件没有损坏。",
                    detail=str(exc),
                )

    def _apply_model_config(self, path):
        config = self.model_registry.get(path)
        if config is None:
            config = infer_model_config(
                path,
                confidence=self.detector.confidence,
                iou_threshold=self.detector.iou_threshold,
            )
        self.detector.apply_model_config(config)
        self.model_config = config
        self.model_registry.save(config)
        self.conf_slider.set(config.confidence)
        self.iou_slider.set(config.iou_threshold)
        self._on_conf_change(config.confidence)
        self._on_iou_change(config.iou_threshold)

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="打开影像",
            filetypes=[("影像文件", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp")],
        )
        if path:
            if confirm_import(self, path, "image"):
                self._load_image_path(path)

    def _load_image_path(self, path, record: bool = True):
        self.current_image = utils.imread_chinese(path)
        if self.current_image is not None:
            self.current_image_path = path
            if record:
                source = record_data_source(self, path, "raster")
                self.current_geo_transform = (source or {}).get(
                    "transform"
                ) or raster_geo_transform(path)
            else:
                self.current_geo_transform = raster_geo_transform(path)
            self.result_image = None
            self.last_output = None
            self._show_image(self.current_image)
            self.detect_status.configure(
                text=f"已加载: {os.path.basename(path)}", text_color=THEME["text_secondary"]
            )
            notify(self, f"影像已加载：{os.path.basename(path)}", "success")
            if self.status_vars.get("image_size"):
                self._update_image_metadata(path)
            if record:
                mark_project_dirty(self)

    def _run_detection(self):
        if not self.detector.available:
            messagebox.showwarning("提示", "请先加载 ONNX 模型")
            return
        if self.current_image is None:
            messagebox.showwarning("提示", "请先打开影像")
            return
        self.detect_status.configure(text="正在检测...", text_color=THEME["warning"])
        self.btn_detect.configure(state=ctk.DISABLED, text="检测中...")
        self.status_vars.get("algorithm") and self.status_vars["algorithm"].set("目标检测中...")

        def work():
            output = self.detector.detect(self.current_image)
            result_image = self.detector.draw_detections(self.current_image, output)
            return output, result_image

        def done(payload):
            output, result_image = payload
            self.last_output = output
            self.result_image = result_image
            self._show_image(self.result_image)
            self._on_detection_done(output)

        def failed(err):
            self.btn_detect.configure(state=ctk.NORMAL, text="执行检测")
            self.detect_status.configure(text="检测失败", text_color=THEME["danger"])
            show_actionable_error(
                self,
                "检测失败",
                "目标检测没有成功完成。",
                "请检查模型输入尺寸、类别配置和影像格式。",
                detail=str(err),
            )

        run_background(self, work, done, failed)

    def _on_detection_done(self, output: DetectionOutput):
        self.btn_detect.configure(state=ctk.NORMAL, text="执行检测")
        self.detect_status.configure(
            text=f"检测到 {output.count} 个目标 ({output.inference_time_ms:.0f}ms)",
            text_color=THEME["success"],
        )
        if self.status_vars.get("features"):
            self.status_vars["features"].set(str(output.count))
        if self.status_vars.get("algorithm"):
            self.status_vars["algorithm"].set("目标检测")
        self._record_result(
            "detection",
            "目标检测",
            inputs=[self.current_image_path, self.detector.model_path],
            params={
                "confidence": self.detector.confidence,
                "iou_threshold": self.detector.iou_threshold,
            },
            metrics={
                "count": output.count,
                "inference_time_ms": round(output.inference_time_ms, 2),
            },
        )
        notify(self, f"检测完成：{output.count} 个目标", "success")

    def _export_result(self):
        if self.result_image is None:
            messagebox.showwarning("提示", "请先执行检测")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("GeoTIFF", "*.tif")],
        )
        if path:
            if self._is_tiff(path) and self._is_tiff(self.current_image_path):
                save_geotiff_like(
                    self.current_image_path,
                    self.result_image,
                    path,
                    color_order="BGR",
                )
            else:
                utils.imwrite_chinese(path, self.result_image)
                if self._is_tiff(self.current_image_path) and not self._is_tiff(path):
                    notify(
                        self,
                        "Spatial reference is not preserved in PNG/JPEG exports.",
                        "warning",
                    )
            metrics = {}
            if self.last_output is not None:
                metrics = {
                    "count": self.last_output.count,
                    "inference_time_ms": round(self.last_output.inference_time_ms, 2),
                }
            self._record_result(
                "detection",
                "导出检测结果",
                inputs=[self.current_image_path, self.detector.model_path],
                outputs=[path],
                params={
                    "confidence": self.detector.confidence,
                    "iou_threshold": self.detector.iou_threshold,
                },
                metrics=metrics,
            )
            notify(self, f"结果已保存：{path}", "success")

    @staticmethod
    def _is_tiff(path):
        return os.path.splitext(str(path))[1].lower() in (".tif", ".tiff")

    def _show_image(self, img):
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.viewer.load(image_array=rgb, geo_transform=self.current_geo_transform)

    def _update_image_metadata(self, path):
        try:
            meta = get_image_metadata(path)
            self.status_vars["image_size"].set(
                f"{meta['width']}×{meta['height']} / {meta['bands']} bands / {meta['dtype']}"
            )
        except Exception:
            h, w = self.current_image.shape[:2]
            self.status_vars["image_size"].set(f"{w}×{h}")

    def _record_result(self, category, title, **kwargs):
        if self.model_config:
            kwargs.setdefault("model_config", self.model_config.to_dict())
        elif self.detector.model_config:
            kwargs.setdefault("model_config", self.detector.model_config)
        return record_project_result(self, category, title, **kwargs)

    def get_state(self):
        return {
            "model_path": self.detector.model_path,
            "image_path": self.current_image_path,
            "confidence": self.detector.confidence,
            "iou_threshold": self.detector.iou_threshold,
            "model_config": self.model_config.to_dict() if self.model_config else {},
        }

    def set_state(self, state):
        if not state:
            return
        confidence = float(state.get("confidence", self.detector.confidence))
        iou = float(state.get("iou_threshold", self.detector.iou_threshold))
        self.conf_slider.set(confidence)
        self.iou_slider.set(iou)
        self._on_conf_change(confidence)
        self._on_iou_change(iou)

        model_path = state.get("model_path", "")
        if model_path and os.path.exists(model_path) and self.detector.load_model(model_path):
            config_payload = state.get("model_config") or {}
            if config_payload:
                self.model_config = ModelConfig.from_dict(config_payload)
                self.detector.apply_model_config(self.model_config)
                self.model_registry.save(self.model_config)
                self.conf_slider.set(self.model_config.confidence)
                self.iou_slider.set(self.model_config.iou_threshold)
                self._on_conf_change(self.model_config.confidence)
                self._on_iou_change(self.model_config.iou_threshold)
            else:
                self._apply_model_config(model_path)
            self.model_path_var.set(os.path.basename(model_path))
            self.detect_status.configure(text="模型已加载", text_color=THEME["success"])

        image_path = state.get("image_path", "")
        if image_path and os.path.exists(image_path):
            self._load_image_path(image_path, record=False)

    def destroy(self):
        """清理资源"""
        self.detector._session = None
        super().destroy()
