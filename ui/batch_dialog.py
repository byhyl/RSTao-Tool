"""批量处理对话框"""

import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.batch_processor import BatchProcessor, BatchResult

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE, THEME
from .ui_helpers import make_button, notify


class BatchDialog(ctk.CTkToplevel):
    """批量处理对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.processor = BatchProcessor(max_workers=4)
        self.result: BatchResult = None
        self.summary_paths = {}
        self._last_batch_context = {}
        self._closing = False

        self.title("批量处理")
        self.geometry("600x500")
        self.resizable(False, False)
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
            text="选择处理类型、输入输出目录后开始批量任务",
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

        # 执行按钮
        self.start_btn = make_button(self, "开始处理", self._start_batch, "primary", height=36)
        self.start_btn.pack(pady=15)

        self._on_type_change()

    def _on_type_change(self):
        is_match = self.task_type.get() == "match"
        if is_match:
            self.template_label.pack(anchor="w", padx=20, pady=(10, 2))
            self.template_row.pack(fill="x", padx=20)
            self.template_entry.pack(side="left", fill="x", expand=True)
            self.template_btn.pack(side="right", padx=(8, 0))
        else:
            self.template_label.pack_forget()
            self.template_row.pack_forget()

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

        self.summary_paths = {}
        self._last_batch_context = {
            "task_type": task_type,
            "input_dir": input_dir,
            "output_dir": output_dir,
            "template": template,
            "recursive": recursive,
            "skip_existing": skip_existing,
        }
        self.progress.set(0)
        self.progress_label.configure(text="正在收集影像文件...")
        self.start_btn.configure(state=ctk.DISABLED, text="处理中...")

        def run():
            try:
                if task_type == "feature":
                    self.result = self.processor.batch_feature_detect(
                        input_dir,
                        output_dir,
                        recursive=recursive,
                        skip_existing=skip_existing,
                    )
                else:
                    self.result = self.processor.batch_match(
                        template,
                        input_dir,
                        output_dir,
                        recursive=recursive,
                        skip_existing=skip_existing,
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
            msg = (
                f"总数: {self.result.total}\n"
                f"成功: {self.result.success}\n"
                f"跳过: {self.result.skipped}\n"
                f"失败: {self.result.failed}\n"
                f"成功率: {self.result.success_rate:.1f}%\n"
                f"耗时: {self.result.elapsed:.1f} 秒"
            )
            if self.summary_paths:
                msg += f"\n摘要: {os.path.basename(self.summary_paths.get('json', 'summary.json'))}"
            self.start_btn.configure(state=ctk.NORMAL, text="开始处理")
            self.progress_label.configure(text=msg)
            self._record_task_history()
            notify(self.parent, "批量处理完成", "success")
        else:
            self.start_btn.configure(state=ctk.NORMAL, text="开始处理")
            messagebox.showwarning("提示", "未找到任何可处理的影像文件")

    def _record_task_history(self):
        pm = getattr(self.parent, "project_manager", None)
        if not pm or not getattr(pm, "current_project", None) or not self.result:
            return
        ctx = self._last_batch_context
        title = "批量特征检测" if ctx.get("task_type") == "feature" else "批量影像匹配"
        outputs = [ctx.get("output_dir", ""), *self.summary_paths.values()]
        inputs = [ctx.get("input_dir", ""), ctx.get("template", "")]
        pm.add_task_record(
            title,
            inputs=[p for p in inputs if p],
            outputs=[p for p in outputs if p],
            params={
                "recursive": ctx.get("recursive", False),
                "skip_existing": ctx.get("skip_existing", False),
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
