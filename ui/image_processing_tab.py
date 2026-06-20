"""Image processing workspace tab."""

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
import numpy as np

from core.image_processing import ImageProcessingCore, OperatorSpec, ParameterSpec
from data.image_io import get_image_metadata, read_raster_data, save_raster_result

from .error_dialog import show_actionable_error
from .import_preview_dialog import confirm_import
from .raster_viewer import RasterViewer
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME, CollapsibleCard
from .ui_helpers import (
    make_button,
    mark_project_dirty,
    notify,
    raster_geo_transform,
    record_data_source,
    record_project_result,
    run_background,
)


class OperatorHelpWindow(ctk.CTkToplevel):
    """Non-modal operator documentation window."""

    def __init__(self, parent, spec: OperatorSpec, core: ImageProcessingCore):
        super().__init__(parent)
        self.title("算子说明")
        self.geometry("460x520")
        self.minsize(380, 360)
        self.configure(fg_color=THEME["bg"])
        self.transient(parent.winfo_toplevel())

        self.title_label = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SUBTITLE,
            text_color=THEME["text_primary"],
            anchor="w",
        )
        self.title_label.pack(fill="x", padx=16, pady=(14, 6))
        self.textbox = ctk.CTkTextbox(
            self,
            font=FONT_SMALL,
            fg_color=THEME["card"],
            text_color=THEME["text_primary"],
            border_width=1,
            border_color=THEME["border"],
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.update_spec(spec, core)

    def update_spec(self, spec: OperatorSpec, core: ImageProcessingCore):
        self.title_label.configure(text=f"{spec.name} · {spec.category}")
        text = self._build_text(spec, core)
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self.textbox.configure(state="disabled")

    def _build_text(self, spec: OperatorSpec, core: ImageProcessingCore) -> str:
        lines = [
            "简介",
            spec.description,
            "",
            "使用说明",
            spec.usage or spec.description,
            "",
            "适用性",
            f"- 彩色影像：{'支持' if spec.supports_color else '不支持'}",
            f"- 多波段影像：{'支持' if spec.supports_multiband else '以预览/前三波段处理'}",
        ]
        if not spec.parameters:
            lines.extend(["", "参数", "- 无需额外参数"])
            return "\n".join(lines)

        lines.extend(["", "参数"])
        for param in spec.parameters:
            line = f"- {param.label}"
            if param.kind == "choice" and param.options:
                options = "、".join(param.display_value(option) for option in param.options)
                line += f"：{options}"
            elif param.min_value is not None and param.max_value is not None:
                line += f"：范围 {param.min_value} - {param.max_value}"
            if param.visible_when:
                parts = []
                for dep_name, values in param.visible_when.items():
                    dep = next((item for item in spec.parameters if item.name == dep_name), None)
                    labels = [dep.display_value(value) if dep else str(value) for value in values]
                    dep_label = dep.label if dep else dep_name
                    parts.append(f"{dep_label}为{'/'.join(labels)}")
                line += f"（仅当{'，'.join(parts)}时显示）"
            if param.help_text:
                line += f"。{param.help_text}"
            lines.append(line)
        return "\n".join(lines)


class ImageProcessingTab(ctk.CTkFrame):
    """Commercial-grade basic image processing surface."""

    def __init__(self, parent, status_vars):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self.status_vars = status_vars
        self.core = ImageProcessingCore()

        self.image_path = ""
        self.reference_path = ""
        self.original_img = None
        self.reference_img = None
        self.result_img = None
        self.geo_transform = None
        self.last_metrics = {}

        self.category_var = ctk.StringVar(value="")
        self.operator_var = ctk.StringVar(value="")
        self.param_vars = {}
        self.param_values = {}
        self.operator_name_to_id = {}
        self.help_window = None

        self._build_ui()
        self._init_operator_controls()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=300)
        self.grid_columnconfigure(1, weight=3)

        self.control_scroll = ctk.CTkScrollableFrame(self, **PANEL_STYLE)
        self.control_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.display_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.display_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self._build_controls()
        self._build_display()

    def _build_controls(self):
        data_card = CollapsibleCard(self.control_scroll, "数据管理")
        data_card.pack(fill="x", pady=5, padx=5)
        make_button(data_card.content, "加载影像", self.load_image, "primary", icon="open").pack(
            fill="x", pady=3, padx=5
        )
        make_button(
            data_card.content, "加载参考影像", self.load_reference_image, "secondary", icon="open"
        ).pack(fill="x", pady=3, padx=5)
        make_button(data_card.content, "保存结果", self.save_result, "secondary", icon="save").pack(
            fill="x", pady=3, padx=5
        )
        make_button(data_card.content, "重置结果", self.reset_result).pack(fill="x", pady=3, padx=5)
        self.data_label = ctk.CTkLabel(
            data_card.content,
            text="未加载影像",
            wraplength=250,
            justify="left",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        )
        self.data_label.pack(fill="x", pady=(6, 2), padx=5)
        self.reference_label = ctk.CTkLabel(
            data_card.content,
            text="参考影像：未加载",
            wraplength=250,
            justify="left",
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
        )
        self.reference_label.pack(fill="x", pady=(0, 4), padx=5)

        op_card = CollapsibleCard(self.control_scroll, "处理算子")
        op_card.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(op_card.content, text="类别", font=FONT_NORMAL).pack(
            anchor="w", padx=5, pady=(5, 2)
        )
        self.category_menu = ctk.CTkOptionMenu(
            op_card.content,
            variable=self.category_var,
            values=[""],
            command=lambda _value: self._refresh_operator_menu(),
        )
        self.category_menu.pack(fill="x", pady=2, padx=5)

        ctk.CTkLabel(op_card.content, text="算子", font=FONT_NORMAL).pack(
            anchor="w", padx=5, pady=(8, 2)
        )
        self.operator_menu = ctk.CTkOptionMenu(
            op_card.content,
            variable=self.operator_var,
            values=[""],
            command=lambda _value: self._refresh_params(),
        )
        self.operator_menu.pack(fill="x", pady=2, padx=5)
        self.operator_desc = ctk.CTkLabel(
            op_card.content,
            text="",
            wraplength=250,
            justify="left",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        )
        self.operator_desc.pack(fill="x", pady=(6, 0), padx=5)
        make_button(op_card.content, "算子说明", self.show_operator_help, "secondary").pack(
            fill="x", pady=(8, 2), padx=5
        )

        self.param_card = CollapsibleCard(self.control_scroll, "参数")
        self.param_card.pack(fill="x", pady=5, padx=5)
        self.param_frame = self.param_card.content

        action_card = CollapsibleCard(self.control_scroll, "执行")
        action_card.pack(fill="x", pady=5, padx=5)
        self.run_btn = make_button(
            action_card.content, "预览 / 执行", self.apply_processing, "primary"
        )
        self.run_btn.pack(fill="x", pady=3, padx=5)
        self.metrics_label = ctk.CTkLabel(
            action_card.content,
            text="等待处理",
            wraplength=250,
            justify="left",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        )
        self.metrics_label.pack(fill="x", pady=(8, 2), padx=5)

    def _build_display(self):
        self.coord_var = ctk.StringVar(value="")
        coord_bar = ctk.CTkFrame(self.display_frame, height=22, fg_color=THEME["statusbar"])
        coord_bar.pack(fill="x", side="top")
        ctk.CTkLabel(
            coord_bar,
            textvariable=self.coord_var,
            font=("Consolas", 9),
            text_color=THEME["text_secondary"],
        ).pack(side="left", padx=8)

        top = ctk.CTkFrame(self.display_frame, fg_color="transparent")
        top.pack(fill="both", expand=True)

        left = ctk.CTkFrame(top, fg_color=THEME["card"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 1))
        ctk.CTkLabel(
            left, text=" 原始影像", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_original = RasterViewer(left)
        self.viewer_original.pack(fill="both", expand=True)

        right = ctk.CTkFrame(top, fg_color=THEME["card"])
        right.pack(side="right", fill="both", expand=True, padx=(1, 0))
        ctk.CTkLabel(
            right, text=" 处理结果", font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=4, pady=1)
        self.viewer_result = RasterViewer(right)
        self.viewer_result.pack(fill="both", expand=True)

        self.viewer_original._on_coord_change = lambda text: self.coord_var.set(text)
        self.viewer_result._on_coord_change = lambda text: self.coord_var.set(text)

    def _init_operator_controls(self):
        categories = self.core.categories()
        if not categories:
            return
        self.category_menu.configure(values=categories)
        self.category_var.set(categories[0])
        self._refresh_operator_menu()

    def _refresh_operator_menu(self):
        specs = self.core.list_operators(self.category_var.get())
        values = [spec.name for spec in specs] or [""]
        self.operator_name_to_id = {spec.name: spec.id for spec in specs}
        self.operator_menu.configure(values=values)
        self.operator_var.set(values[0])
        self._refresh_params()

    def _current_operator_id(self):
        return self.operator_name_to_id.get(self.operator_var.get(), "")

    def _current_spec(self) -> OperatorSpec | None:
        operator_id = self._current_operator_id()
        return self.core.get_operator(operator_id) if operator_id else None

    def _refresh_params(self):
        self._store_current_param_values()
        for widget in self.param_frame.winfo_children():
            widget.destroy()
        self.param_vars = {}
        spec = self._current_spec()
        if not spec:
            return
        self.operator_desc.configure(text=spec.description)
        defaults = self.core.default_params(spec.id)
        defaults.update({k: v for k, v in self.param_values.items() if k in defaults})
        active_params = self.core.active_parameters(spec.id, defaults)
        if not active_params:
            ctk.CTkLabel(
                self.param_frame,
                text="该算子无需额外参数",
                font=FONT_SMALL,
                text_color=THEME["text_muted"],
            ).pack(anchor="w", padx=5, pady=4)
            self._update_help_window_if_open()
            return
        for param in active_params:
            self._add_param_control(param, defaults.get(param.name, param.default))
        self._update_help_window_if_open()

    def _add_param_control(self, param: ParameterSpec, value=None):
        frame = ctk.CTkFrame(self.param_frame, fg_color="transparent")
        frame.pack(fill="x", pady=4, padx=5)
        ctk.CTkLabel(frame, text=param.label, font=FONT_NORMAL).pack(anchor="w")

        if param.kind == "choice":
            raw_value = param.raw_value(param.default if value is None else value)
            var = ctk.StringVar(value=param.display_value(raw_value))
            menu = ctk.CTkOptionMenu(
                frame,
                variable=var,
                values=list(param.display_options()),
                command=lambda _value, name=param.name: self._on_choice_param_changed(name),
            )
            menu.pack(fill="x", pady=(2, 0))
            self.param_vars[param.name] = (param, var)
            return

        var = ctk.StringVar(value=str(param.default if value is None else value))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        entry = ctk.CTkEntry(row, textvariable=var, width=70, font=FONT_SMALL)
        entry.pack(side="right", padx=(6, 0))
        if param.min_value is not None and param.max_value is not None:
            slider_var = ctk.DoubleVar(value=float(param.default))
            slider = ctk.CTkSlider(
                row,
                from_=float(param.min_value),
                to=float(param.max_value),
                variable=slider_var,
                command=lambda value, target=var, spec=param: target.set(
                    self._format_param_value(spec, value)
                ),
            )
            slider.pack(side="left", fill="x", expand=True)
        self.param_vars[param.name] = (param, var)

    def _on_choice_param_changed(self, name):
        if name in self.param_vars:
            param, var = self.param_vars[name]
            self.param_values[name] = param.raw_value(var.get())
        self._refresh_params()

    def _store_current_param_values(self):
        for name, (param, var) in self.param_vars.items():
            value = var.get()
            try:
                if param.kind in {"int", "odd"}:
                    number = int(round(float(value)))
                    if param.kind == "odd" and number % 2 == 0:
                        number += 1
                    self.param_values[name] = number
                elif param.kind == "float":
                    self.param_values[name] = float(value)
                elif param.kind == "choice":
                    self.param_values[name] = param.raw_value(value)
                else:
                    self.param_values[name] = value
            except Exception:
                self.param_values[name] = value

    def _format_param_value(self, param: ParameterSpec, value):
        if param.kind in {"int", "odd"}:
            number = int(round(float(value)))
            if param.kind == "odd" and number % 2 == 0:
                number += 1
            return str(number)
        return f"{float(value):.3f}"

    def _collect_params(self):
        params = {}
        for name, (spec, var) in self.param_vars.items():
            value = var.get()
            if spec.kind in {"int", "odd"}:
                number = int(round(float(value)))
                if spec.kind == "odd" and number % 2 == 0:
                    number += 1
                params[name] = number
            elif spec.kind == "float":
                params[name] = float(value)
            elif spec.kind == "choice":
                params[name] = spec.raw_value(value)
            else:
                params[name] = value
        if self._current_operator_id() == "hist_match_reference" and self.reference_img is not None:
            params["reference_image"] = self.reference_img
        return params

    def show_operator_help(self):
        spec = self._current_spec()
        if not spec:
            return
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.update_spec(spec, self.core)
            self.help_window.lift()
            return
        self.help_window = OperatorHelpWindow(self, spec, self.core)

    def _update_help_window_if_open(self):
        if self.help_window and self.help_window.winfo_exists():
            spec = self._current_spec()
            if spec:
                self.help_window.update_spec(spec, self.core)

    def load_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("影像文件", "*.tif;*.tiff;*.png;*.jpg;*.jpeg;*.bmp;*.img;*.jp2")]
        )
        if path:
            if confirm_import(self, path, "image"):
                self._load_image_from_path(path)

    def load_image_silent(self, path, preview: bool = True):
        if preview and not confirm_import(self, path, "image"):
            return
        self._load_image_from_path(path)

    def _load_image_from_path(self, path):
        try:
            self.image_path = path
            self.original_img = read_raster_data(path, preserve_dtype=True)
            self.result_img = None
            source = record_data_source(self, path, "raster")
            self.geo_transform = (source or {}).get("transform") or raster_geo_transform(path)
            self.viewer_original.load(
                image_array=self.core.to_display_rgb(self.original_img),
                geo_transform=self.geo_transform,
            )
            self.viewer_result.clear_image()
            self._update_image_metadata(path)
            self.data_label.configure(text=os.path.basename(path))
            self.metrics_label.configure(text="影像已加载，等待处理")
            mark_project_dirty(self)
            notify(self, f"影像加载完成：{os.path.basename(path)}", "success")
        except Exception as exc:
            show_actionable_error(
                self,
                "影像加载失败",
                "影像文件没有成功导入。",
                "请确认文件没有损坏，或安装 rasterio 后重试多波段格式。",
                detail=str(exc),
            )

    def load_reference_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("影像文件", "*.tif;*.tiff;*.png;*.jpg;*.jpeg;*.bmp;*.img;*.jp2")]
        )
        if not path:
            return
        try:
            self.reference_path = path
            self.reference_img = read_raster_data(path, preserve_dtype=True)
            self.reference_label.configure(text=f"参考影像：{os.path.basename(path)}")
            notify(self, "参考影像已加载", "success")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def apply_processing(self):
        if self.original_img is None:
            messagebox.showwarning("提示", "请先加载影像")
            return
        operator_id = self._current_operator_id()
        if not operator_id:
            messagebox.showwarning("提示", "请选择处理算子")
            return
        try:
            params = self._collect_params()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        self.run_btn.configure(state=ctk.DISABLED, text="处理中...")
        self.metrics_label.configure(text="正在处理...")
        source = np.asarray(self.original_img).copy()

        def work():
            return self.core.process(source, operator_id, params)

        def done(result):
            self.result_img = result.image
            self.last_metrics = result.metrics
            display = result.display_image if result.display_image is not None else result.image
            self.viewer_result.load(
                image_array=self.core.to_display_rgb(display),
                geo_transform=self.geo_transform,
            )
            self._update_metrics_label()
            self.run_btn.configure(state=ctk.NORMAL, text="预览 / 执行")
            self.status_vars["algorithm"].set(result.metrics.get("operator", operator_id))
            self.status_vars["features"].set("已处理")
            notify(self, "图像处理完成", "success")

        def error(exc):
            self.run_btn.configure(state=ctk.NORMAL, text="预览 / 执行")
            self.metrics_label.configure(text="处理失败")
            messagebox.showerror("处理失败", str(exc))

        run_background(self, work, done, error)

    def _update_metrics_label(self):
        metrics = self.last_metrics or {}
        shape = metrics.get("shape", "")
        text = [
            f"算子：{metrics.get('operator', '')}",
            f"尺寸：{shape}",
            f"类型：{metrics.get('dtype', '')}",
            f"最小/最大：{self._fmt_metric(metrics.get('min'))} / {self._fmt_metric(metrics.get('max'))}",
            f"均值/标准差：{self._fmt_metric(metrics.get('mean'))} / {self._fmt_metric(metrics.get('std'))}",
        ]
        if "explained_ratio" in metrics:
            text.append(f"PCA贡献率：{metrics['explained_ratio']:.4f}")
        self.metrics_label.configure(text="\n".join(text))

    @staticmethod
    def _fmt_metric(value):
        try:
            return f"{float(value):.3f}"
        except Exception:
            return "-"

    def save_result(self):
        if self.result_img is None:
            messagebox.showwarning("提示", "请先执行处理")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG影像", "*.png"), ("JPG影像", "*.jpg"), ("GeoTIFF", "*.tif")],
        )
        if not path:
            return
        try:
            save_raster_result(self.image_path, self.result_img, path, color_order="RGB")
            operator_id = self._current_operator_id()
            record_project_result(
                self,
                "image_processing",
                "导出图像处理结果",
                inputs=[self.image_path, self.reference_path],
                outputs=[path],
                params={
                    "operator_id": operator_id,
                    "operator": self.operator_var.get(),
                    **self._safe_params_for_record(),
                },
                metrics=self.last_metrics,
            )
            notify(self, f"结果已保存：{path}", "success")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _safe_params_for_record(self):
        params = self._collect_params()
        params.pop("reference_image", None)
        if self.reference_path:
            params["reference_path"] = self.reference_path
        return params

    def reset_result(self):
        self.result_img = None
        self.last_metrics = {}
        self.viewer_result.clear_image()
        self.metrics_label.configure(text="等待处理")

    def _update_image_metadata(self, path):
        try:
            meta = get_image_metadata(path)
            self.status_vars["image_size"].set(
                f"{meta['width']}x{meta['height']} / {meta['bands']} bands / {meta['dtype']}"
            )
        except Exception:
            if self.original_img is not None:
                h, w = self.original_img.shape[:2]
                bands = self.original_img.shape[2] if self.original_img.ndim == 3 else 1
                self.status_vars["image_size"].set(f"{w}x{h} / {bands} bands")

    def get_state(self):
        return {
            "image_path": self.image_path,
            "reference_path": self.reference_path,
            "category": self.category_var.get(),
            "operator": self.operator_var.get(),
            "operator_id": self._current_operator_id(),
            "params": self._safe_params_for_record(),
        }

    def set_state(self, state):
        if not state:
            return
        category = state.get("category")
        if category in self.core.categories():
            self.category_var.set(category)
            self._refresh_operator_menu()
        operator_id = state.get("operator_id")
        if operator_id:
            try:
                spec = self.core.get_operator(operator_id)
                if spec.category != self.category_var.get():
                    self.category_var.set(spec.category)
                    self._refresh_operator_menu()
                self.operator_var.set(spec.name)
            except Exception:
                pass
        params = state.get("params", {})
        self.param_values.update(params)
        self._refresh_params()
        image_path = state.get("image_path", "")
        if image_path and os.path.exists(image_path):
            self._load_image_from_path(image_path)
        reference_path = state.get("reference_path", "")
        if reference_path and os.path.exists(reference_path):
            try:
                self.reference_path = reference_path
                self.reference_img = read_raster_data(reference_path, preserve_dtype=True)
                self.reference_label.configure(text=f"参考影像：{os.path.basename(reference_path)}")
            except Exception:
                pass
