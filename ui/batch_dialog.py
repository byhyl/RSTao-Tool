"""批量处理对话框"""

import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.batch_processor import BatchProcessor, BatchResult, BatchTask
from core.image_processing import ImageProcessingCore, ParameterSpec

from .image_processing_tab import OperatorHelpWindow
from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME
from .ui_helpers import make_button, notify


class BatchDialog(ctk.CTkToplevel):
    """批量处理对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.processor = BatchProcessor(max_workers=4)
        self.image_core = ImageProcessingCore()
        self.result: BatchResult = None
        self.summary_paths = {}
        self._last_batch_context = {}
        self._task_rows = {}
        self._running_paths = []
        self._closing = False
        self.processing_param_vars = {}
        self.processing_param_values = {}
        self.operator_name_to_id = {}
        self.processing_help_window = None

        self.title("批量处理")
        self.geometry("880x680")
        self.minsize(760, 580)
        self.resizable(True, True)
        self.configure(fg_color=THEME["bg"])

        self._create_ui()
        self.focus()
        self.grab_set()

    def _create_ui(self):
        # 标题
        ctk.CTkLabel(self, text="批量处理", font=("Microsoft YaHei UI", 18, "bold")).pack(
            pady=(20, 5)
        )
        ctk.CTkLabel(
            self,
            text="选择处理类型、输入输出目录后开始批量任务，可查看每个文件状态并重试失败项",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
        ).pack(pady=(0, 15))

        # 处理类型
        type_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        type_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(type_frame, text="处理类型", font=FONT_NORMAL).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.task_type = ctk.StringVar(value="feature")
        type_row = ctk.CTkFrame(type_frame, fg_color="transparent")
        type_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkRadioButton(
            type_row,
            text="批量特征检测",
            variable=self.task_type,
            value="feature",
            command=self._on_type_change,
            font=FONT_SMALL,
        ).pack(side="left")
        ctk.CTkRadioButton(
            type_row,
            text="批量影像匹配",
            variable=self.task_type,
            value="match",
            command=self._on_type_change,
            font=FONT_SMALL,
        ).pack(side="left", padx=20)
        ctk.CTkRadioButton(
            type_row,
            text="批量图像处理",
            variable=self.task_type,
            value="image_process",
            command=self._on_type_change,
            font=FONT_SMALL,
        ).pack(side="left")

        # 输入目录
        ctk.CTkLabel(self, text="输入目录", font=FONT_NORMAL).pack(
            anchor="w", padx=20, pady=(12, 2)
        )
        in_row = ctk.CTkFrame(self, fg_color="transparent")
        in_row.pack(fill="x", padx=20)
        self.input_entry = ctk.CTkEntry(in_row, font=FONT_SMALL)
        self.input_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            in_row, text="浏览", command=self._browse_input, width=60, font=FONT_SMALL, height=28
        ).pack(side="right", padx=(8, 0))

        # 模板影像（仅匹配模式）
        self.template_label = ctk.CTkLabel(self, text="模板影像", font=FONT_NORMAL)
        self.template_row = ctk.CTkFrame(self, fg_color="transparent")
        self.template_entry = ctk.CTkEntry(self.template_row, font=FONT_SMALL)
        self.template_btn = ctk.CTkButton(
            self.template_row,
            text="浏览",
            command=self._browse_template,
            width=60,
            font=FONT_SMALL,
            height=28,
        )

        # 图像处理算子（仅图像处理模式）
        self.processing_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        ctk.CTkLabel(self.processing_frame, text="图像处理算子", font=FONT_NORMAL).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        proc_row = ctk.CTkFrame(self.processing_frame, fg_color="transparent")
        proc_row.pack(fill="x", padx=12, pady=(0, 8))
        self.processing_category = ctk.StringVar(value="")
        self.processing_operator = ctk.StringVar(value="")
        self.processing_category_menu = ctk.CTkOptionMenu(
            proc_row,
            variable=self.processing_category,
            values=[""],
            command=lambda _value: self._refresh_processing_operators(),
            width=160,
        )
        self.processing_category_menu.pack(side="left", padx=(0, 8))
        self.processing_operator_menu = ctk.CTkOptionMenu(
            proc_row,
            variable=self.processing_operator,
            values=[""],
            command=lambda _value: self._refresh_processing_params(),
            width=220,
        )
        self.processing_operator_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            proc_row,
            text="说明",
            command=self._show_processing_help,
            width=58,
            height=28,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
        ).pack(side="left", padx=(8, 0))
        self.processing_params_frame = ctk.CTkFrame(self.processing_frame, fg_color="transparent")
        self.processing_params_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.reference_row = ctk.CTkFrame(self.processing_frame, fg_color="transparent")
        self.reference_entry = ctk.CTkEntry(self.reference_row, font=FONT_SMALL)
        self.reference_btn = ctk.CTkButton(
            self.reference_row,
            text="参考影像",
            command=self._browse_reference,
            width=84,
            font=FONT_SMALL,
            height=28,
        )
        self.output_format_var = ctk.StringVar(value=".png")
        format_row = ctk.CTkFrame(self.processing_frame, fg_color="transparent")
        format_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(format_row, text="输出格式", font=FONT_SMALL).pack(side="left")
        ctk.CTkOptionMenu(
            format_row,
            variable=self.output_format_var,
            values=[".png", ".jpg", ".tif"],
            width=100,
        ).pack(side="left", padx=(8, 0))
        self._init_processing_controls()

        # 输出目录
        ctk.CTkLabel(self, text="输出目录", font=FONT_NORMAL).pack(
            anchor="w", padx=20, pady=(12, 2)
        )
        out_row = ctk.CTkFrame(self, fg_color="transparent")
        out_row.pack(fill="x", padx=20)
        self.output_entry = ctk.CTkEntry(out_row, font=FONT_SMALL)
        self.output_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            out_row, text="浏览", command=self._browse_output, width=60, font=FONT_SMALL, height=28
        ).pack(side="right", padx=(8, 0))

        # 子目录递归
        self.recursive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="包含子目录", variable=self.recursive_var, font=FONT_SMALL).pack(
            anchor="w", padx=20, pady=(10, 5)
        )
        self.skip_existing_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self, text="跳过已存在结果", variable=self.skip_existing_var, font=FONT_SMALL
        ).pack(anchor="w", padx=20, pady=(0, 5))

        # 进度
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=20, pady=(10, 2))
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(
            self, text="", font=FONT_SMALL, text_color=THEME["text_secondary"]
        )
        self.progress_label.pack()

        # 任务列表
        table_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        table_frame.pack(fill="both", expand=True, padx=20, pady=(8, 6))
        header = ctk.CTkFrame(table_frame, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 2))
        for text, width in [("状态", 70), ("文件", 260), ("耗时", 70), ("结果/错误", 360)]:
            ctk.CTkLabel(header, text=text, width=width, anchor="w", font=FONT_SMALL).pack(
                side="left", padx=4
            )
        self.task_list = ctk.CTkScrollableFrame(table_frame, fg_color=THEME["card"], height=180)
        self.task_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.summary_label = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
            justify="left",
        )
        self.summary_label.pack(fill="x", padx=20, pady=(2, 4))

        # 执行按钮
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 15))
        self.start_btn = make_button(btn_row, "开始处理", self._start_batch, "primary", height=34)
        self.start_btn.pack(side="left", padx=4)
        self.retry_btn = make_button(
            btn_row, "重试失败项", self._retry_failed, "secondary", height=34
        )
        self.retry_btn.configure(state=ctk.DISABLED)
        self.retry_btn.pack(side="left", padx=4)
        self.open_output_btn = make_button(
            btn_row, "打开输出目录", self._open_output_dir, "secondary", height=34
        )
        self.open_output_btn.configure(state=ctk.DISABLED)
        self.open_output_btn.pack(side="left", padx=4)
        self.open_summary_btn = make_button(
            btn_row, "打开摘要", self._open_summary, "secondary", height=34
        )
        self.open_summary_btn.configure(state=ctk.DISABLED)
        self.open_summary_btn.pack(side="left", padx=4)

        self._on_type_change()

    def _on_type_change(self):
        is_match = self.task_type.get() == "match"
        is_processing = self.task_type.get() == "image_process"
        if is_match:
            self.template_label.pack(anchor="w", padx=20, pady=(10, 2))
            self.template_row.pack(fill="x", padx=20)
            self.template_entry.pack(side="left", fill="x", expand=True)
            self.template_btn.pack(side="right", padx=(8, 0))
        else:
            self.template_label.pack_forget()
            self.template_row.pack_forget()
        if is_processing:
            self.processing_frame.pack(
                fill="x", padx=20, pady=(8, 5), before=self.output_entry.master
            )
            self._refresh_reference_row()
        else:
            self.processing_frame.pack_forget()

    def _init_processing_controls(self):
        categories = self.image_core.categories()
        if not categories:
            return
        self.processing_category_menu.configure(values=categories)
        self.processing_category.set(categories[0])
        self._refresh_processing_operators()

    def _refresh_processing_operators(self):
        specs = self.image_core.list_operators(self.processing_category.get())
        values = [spec.name for spec in specs] or [""]
        self.operator_name_to_id = {spec.name: spec.id for spec in specs}
        self.processing_operator_menu.configure(values=values)
        self.processing_operator.set(values[0])
        self._refresh_processing_params()

    def _current_processing_operator_id(self):
        return self.operator_name_to_id.get(self.processing_operator.get(), "")

    def _refresh_processing_params(self):
        self._store_processing_param_values()
        for widget in self.processing_params_frame.winfo_children():
            widget.destroy()
        self.processing_param_vars = {}
        operator_id = self._current_processing_operator_id()
        if not operator_id:
            return
        spec = self.image_core.get_operator(operator_id)
        defaults = self.image_core.default_params(operator_id)
        defaults.update({k: v for k, v in self.processing_param_values.items() if k in defaults})
        active_params = self.image_core.active_parameters(operator_id, defaults)
        if not active_params:
            ctk.CTkLabel(
                self.processing_params_frame,
                text="该算子无需额外参数",
                font=FONT_SMALL,
                text_color=THEME["text_muted"],
            ).pack(anchor="w")
        for param in active_params:
            self._add_processing_param(param, defaults.get(param.name, param.default))
        self._refresh_reference_row()
        self._update_processing_help_if_open()

    def _add_processing_param(self, param: ParameterSpec, value=None):
        row = ctk.CTkFrame(self.processing_params_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=param.label, width=92, anchor="w", font=FONT_SMALL).pack(side="left")
        if param.kind == "choice":
            raw_value = param.raw_value(param.default if value is None else value)
            var = ctk.StringVar(value=param.display_value(raw_value))
            ctk.CTkOptionMenu(
                row,
                variable=var,
                values=list(param.display_options()),
                command=lambda _value, name=param.name: self._on_processing_choice_changed(name),
                width=150,
            ).pack(side="left", fill="x", expand=True)
        else:
            var = ctk.StringVar(value=str(param.default if value is None else value))
            ctk.CTkEntry(row, textvariable=var, font=FONT_SMALL, height=26).pack(
                side="left", fill="x", expand=True
            )
        self.processing_param_vars[param.name] = (param, var)

    def _on_processing_choice_changed(self, name):
        if name in self.processing_param_vars:
            param, var = self.processing_param_vars[name]
            self.processing_param_values[name] = param.raw_value(var.get())
        self._refresh_processing_params()

    def _store_processing_param_values(self):
        for name, (param, var) in self.processing_param_vars.items():
            value = var.get()
            try:
                if param.kind in {"int", "odd"}:
                    number = int(round(float(value)))
                    if param.kind == "odd" and number % 2 == 0:
                        number += 1
                    self.processing_param_values[name] = number
                elif param.kind == "float":
                    self.processing_param_values[name] = float(value)
                elif param.kind == "choice":
                    self.processing_param_values[name] = param.raw_value(value)
                else:
                    self.processing_param_values[name] = value
            except Exception:
                self.processing_param_values[name] = value

    def _refresh_reference_row(self):
        if self._current_processing_operator_id() == "hist_match_reference":
            self.reference_row.pack(fill="x", padx=12, pady=(0, 8))
            self.reference_entry.pack(side="left", fill="x", expand=True)
            self.reference_btn.pack(side="right", padx=(8, 0))
        else:
            self.reference_row.pack_forget()

    def _collect_processing_params(self):
        params = {}
        for name, (spec, var) in self.processing_param_vars.items():
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
        reference = self.reference_entry.get().strip()
        if self._current_processing_operator_id() == "hist_match_reference":
            if not reference or not os.path.isfile(reference):
                raise ValueError("请选择参考影像")
            params["reference_path"] = reference
        return params

    def _show_processing_help(self):
        operator_id = self._current_processing_operator_id()
        if not operator_id:
            return
        spec = self.image_core.get_operator(operator_id)
        if self.processing_help_window and self.processing_help_window.winfo_exists():
            self.processing_help_window.update_spec(spec, self.image_core)
            self.processing_help_window.lift()
            return
        self.processing_help_window = OperatorHelpWindow(self, spec, self.image_core)

    def _update_processing_help_if_open(self):
        if self.processing_help_window and self.processing_help_window.winfo_exists():
            operator_id = self._current_processing_operator_id()
            if operator_id:
                self.processing_help_window.update_spec(
                    self.image_core.get_operator(operator_id), self.image_core
                )

    def _browse_input(self):
        d = filedialog.askdirectory(title="选择输入目录")
        if d:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, d)

    def _browse_template(self):
        f = filedialog.askopenfilename(
            title="选择模板影像", filetypes=[("影像文件", "*.png *.jpg *.tif *.tiff *.bmp")]
        )
        if f:
            self.template_entry.delete(0, "end")
            self.template_entry.insert(0, f)

    def _browse_reference(self):
        f = filedialog.askopenfilename(
            title="选择参考影像",
            filetypes=[("影像文件", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.img *.jp2")],
        )
        if f:
            self.reference_entry.delete(0, "end")
            self.reference_entry.insert(0, f)

    def _browse_output(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, d)

    def _start_batch(self):
        input_dir = self.input_entry.get().strip()
        output_dir = self.output_entry.get().strip()

        if not input_dir or not output_dir:
            messagebox.showwarning("提示", "请选择输入和输出目录")
            return

        if not os.path.isdir(input_dir):
            messagebox.showerror("错误", "输入目录不存在")
            return

        os.makedirs(output_dir, exist_ok=True)

        recursive = self.recursive_var.get()
        skip_existing = self.skip_existing_var.get()
        task_type = self.task_type.get()
        template = self.template_entry.get().strip()
        if task_type == "match" and (not template or not os.path.isfile(template)):
            messagebox.showerror("错误", "请选择模板影像")
            return
        processing_operator = self._current_processing_operator_id()
        processing_params = {}
        if task_type == "image_process":
            if not processing_operator:
                messagebox.showerror("错误", "请选择图像处理算子")
                return
            try:
                processing_params = self._collect_processing_params()
            except Exception as e:
                messagebox.showerror("参数错误", str(e))
                return

        images = self.processor.collect_images(input_dir, recursive)
        if not images:
            messagebox.showwarning("提示", "未找到任何可处理的影像文件")
            return

        self.summary_paths = {}
        self._last_batch_context = {
            "task_type": task_type,
            "input_dir": input_dir,
            "output_dir": output_dir,
            "template": template,
            "processing_operator": processing_operator,
            "processing_operator_name": self.processing_operator.get(),
            "processing_params": processing_params,
            "output_ext": self.output_format_var.get(),
            "recursive": recursive,
            "skip_existing": skip_existing,
        }
        self._run_batch(images, retry=False)

    def _run_batch(self, image_paths, retry: bool = False):
        if not image_paths:
            messagebox.showwarning("提示", "没有可处理的任务")
            return
        ctx = self._last_batch_context
        output_dir = ctx["output_dir"]
        task_type = ctx["task_type"]
        template = ctx.get("template", "")
        skip_existing = ctx.get("skip_existing", False)

        if not retry:
            self.summary_paths = {}
        self._running_paths = list(image_paths)
        self._render_task_rows(self._running_paths, reset=not retry)
        self.progress.set(0)
        self.progress_label.configure(text="正在处理...")
        self.summary_label.configure(text="")
        self.start_btn.configure(state=ctk.DISABLED, text="处理中...")
        self.retry_btn.configure(state=ctk.DISABLED)
        self.open_output_btn.configure(state=ctk.DISABLED)
        self.open_summary_btn.configure(state=ctk.DISABLED)

        def run():
            try:
                if task_type == "feature":
                    self.result = self.processor.batch_feature_detect_paths(
                        self._running_paths,
                        output_dir,
                        skip_existing=skip_existing,
                    )
                elif task_type == "match":
                    self.result = self.processor.batch_match_paths(
                        template,
                        self._running_paths,
                        output_dir,
                        skip_existing=skip_existing,
                    )
                else:
                    self.result = self.processor.batch_image_process_paths(
                        self._running_paths,
                        output_dir,
                        ctx.get("processing_operator", ""),
                        params=ctx.get("processing_params", {}),
                        skip_existing=skip_existing,
                        output_ext=ctx.get("output_ext", ".png"),
                    )
                if self.result and self.result.total > 0:
                    self.summary_paths = self.processor.export_summary(self.result, output_dir)

                if not self._closing:
                    self.after(0, self._on_complete)
            except Exception as e:
                if not self._closing:
                    self.after(
                        0,
                        lambda err=e: (
                            self.start_btn.configure(state=ctk.NORMAL, text="开始处理"),
                            messagebox.showerror("错误", str(err)),
                        ),
                    )

        self.processor.on_task_update(
            lambda task, c, t: (
                not self._closing and self.after(0, self._update_task_row, task, c, t)
            )
        )
        self.processor.on_progress(
            lambda c, t, m: (not self._closing and self.after(0, self._update_progress, c, t, m))
        )
        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, current, total, message):
        self.progress.set(current / total if total > 0 else 0)
        self.progress_label.configure(text=f"{current}/{total} - {message}")

    def destroy(self):
        self._closing = True
        super().destroy()

    def _on_complete(self):
        if self.result and self.result.total > 0:
            msg = self._summary_text(self.result)
            self.start_btn.configure(state=ctk.NORMAL, text="开始处理")
            self.progress_label.configure(text=msg)
            self.summary_label.configure(text=msg)
            self.retry_btn.configure(state=ctk.NORMAL if self.result.failed else ctk.DISABLED)
            self.open_output_btn.configure(state=ctk.NORMAL)
            self.open_summary_btn.configure(
                state=ctk.NORMAL if self.summary_paths else ctk.DISABLED
            )
            self._record_task_history()
            notify(self.parent, "批量处理完成", "success")
        else:
            self.start_btn.configure(state=ctk.NORMAL, text="开始处理")
            messagebox.showwarning("提示", "未找到任何可处理的影像文件")

    def _render_task_rows(self, paths, reset: bool = True):
        if reset:
            for widget in self.task_list.winfo_children():
                widget.destroy()
            self._task_rows = {}
        for path in paths:
            key = os.path.normcase(os.path.abspath(path))
            if key in self._task_rows:
                self._set_task_row(key, "等待", os.path.basename(path), "", "")
                continue
            row = ctk.CTkFrame(self.task_list, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            status = ctk.CTkLabel(row, text="等待", width=70, anchor="w", font=FONT_SMALL)
            name = ctk.CTkLabel(
                row,
                text=os.path.basename(path),
                width=260,
                anchor="w",
                font=FONT_SMALL,
                text_color=THEME["text_secondary"],
            )
            duration = ctk.CTkLabel(row, text="", width=70, anchor="w", font=FONT_SMALL)
            detail = ctk.CTkLabel(
                row,
                text="",
                width=360,
                anchor="w",
                font=FONT_SMALL,
                text_color=THEME["text_muted"],
            )
            for widget in (status, name, duration, detail):
                widget.pack(side="left", padx=4)
            self._task_rows[key] = {
                "status": status,
                "name": name,
                "duration": duration,
                "detail": detail,
            }

    def _update_task_row(self, task: BatchTask, current: int, total: int):
        key = os.path.normcase(os.path.abspath(task.input_path))
        if key not in self._task_rows:
            self._render_task_rows([task.input_path], reset=False)
        detail = task.error or (task.result or "")
        if detail and len(detail) > 62:
            detail = "..." + detail[-59:]
        status_text = {
            "done": "成功",
            "skipped": "跳过",
            "failed": "失败",
            "running": "运行",
            "pending": "等待",
        }.get(task.status, task.status)
        self._set_task_row(
            key,
            status_text,
            os.path.basename(task.input_path),
            f"{task.duration:.1f}s" if task.duration else "",
            detail,
            task.status,
        )
        self.progress.set(current / total if total > 0 else 0)

    def _set_task_row(self, key, status, name, duration, detail, raw_status="pending"):
        row = self._task_rows[key]
        colors = {
            "done": THEME["success"],
            "skipped": THEME["warning"],
            "failed": THEME["danger"],
            "running": THEME["accent"],
            "pending": THEME["text_muted"],
        }
        row["status"].configure(text=status, text_color=colors.get(raw_status, THEME["text_muted"]))
        row["name"].configure(text=name)
        row["duration"].configure(text=duration)
        row["detail"].configure(text=detail)

    def _summary_text(self, result: BatchResult) -> str:
        lines = [
            f"总数 {result.total} | 成功 {result.success} | 跳过 {result.skipped} | 失败 {result.failed}",
            f"成功率 {result.success_rate:.1f}% | 耗时 {result.elapsed:.1f} 秒",
        ]
        if self.summary_paths:
            lines.append(
                f"摘要: {os.path.basename(self.summary_paths.get('json', 'summary.json'))}"
            )
            if self.summary_paths.get("failed_csv"):
                lines.append(f"失败清单: {os.path.basename(self.summary_paths['failed_csv'])}")
        return "\n".join(lines)

    def _retry_failed(self):
        if not self.result:
            return
        failed_paths = [task.input_path for task in self.result.failed_tasks]
        if not failed_paths:
            messagebox.showinfo("提示", "没有失败项需要重试")
            return
        self._run_batch(failed_paths, retry=True)

    def _open_output_dir(self):
        output_dir = self._last_batch_context.get("output_dir", "")
        if output_dir and os.path.isdir(output_dir):
            os.startfile(output_dir)

    def _open_summary(self):
        path = self.summary_paths.get("json") or self.summary_paths.get("csv")
        if path and os.path.exists(path):
            os.startfile(path)

    def _record_task_history(self):
        pm = getattr(self.parent, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None) or not self.result:
            return
        ctx = self._last_batch_context
        if ctx.get("task_type") == "feature":
            title = "批量特征检测"
        elif ctx.get("task_type") == "match":
            title = "批量影像匹配"
        else:
            title = f"批量图像处理 - {ctx.get('processing_operator_name', '')}"
        outputs = [ctx.get("output_dir", ""), *self.summary_paths.values()]
        inputs = [
            ctx.get("input_dir", ""),
            ctx.get("template", ""),
            ctx.get("processing_params", {}).get("reference_path", ""),
        ]
        pm.add_task_record(
            title,
            inputs=[p for p in inputs if p],
            outputs=[p for p in outputs if p],
            params={
                "operator_id": ctx.get("processing_operator", ""),
                "operator": ctx.get("processing_operator_name", ""),
                **ctx.get("processing_params", {}),
                "recursive": ctx.get("recursive", False),
                "skip_existing": ctx.get("skip_existing", False),
                "output_ext": ctx.get("output_ext", ""),
            },
            metrics={
                "total": self.result.total,
                "success": self.result.success,
                "skipped": self.result.skipped,
                "failed": self.result.failed,
                "elapsed": round(self.result.elapsed, 2),
                "success_rate": round(self.result.success_rate, 2),
            },
        )
        if hasattr(self.parent, "_mark_project_dirty"):
            self.parent._mark_project_dirty()
