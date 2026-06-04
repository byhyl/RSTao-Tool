"""批量处理对话框"""
import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.batch_processor import BatchProcessor, BatchResult
from .theme import THEME, FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, PANEL_STYLE


class BatchDialog(ctk.CTkToplevel):
    """批量处理对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.processor = BatchProcessor(max_workers=4)
        self.result: BatchResult = None

        self.title("批量处理")
        self.geometry("600x500")
        self.resizable(False, False)
        self.configure(fg_color=THEME["bg"])

        self._create_ui()
        self.focus()
        self.grab_set()

    def _create_ui(self):
        # 标题
        ctk.CTkLabel(self, text="批量处理", font=("Microsoft YaHei UI", 18, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="选择处理类型、输入输出目录后开始批量任务",
                    font=FONT_SMALL, text_color=THEME["text_secondary"]).pack(pady=(0, 15))

        # 处理类型
        type_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        type_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(type_frame, text="处理类型", font=FONT_NORMAL).pack(anchor="w", padx=12, pady=(10, 2))
        self.task_type = ctk.StringVar(value="feature")
        type_row = ctk.CTkFrame(type_frame, fg_color="transparent")
        type_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkRadioButton(type_row, text="批量特征检测", variable=self.task_type,
                          value="feature", command=self._on_type_change, font=FONT_SMALL).pack(side="left")
        ctk.CTkRadioButton(type_row, text="批量影像匹配", variable=self.task_type,
                          value="match", command=self._on_type_change, font=FONT_SMALL).pack(side="left", padx=20)

        # 输入目录
        ctk.CTkLabel(self, text="输入目录", font=FONT_NORMAL).pack(anchor="w", padx=20, pady=(12, 2))
        in_row = ctk.CTkFrame(self, fg_color="transparent")
        in_row.pack(fill="x", padx=20)
        self.input_entry = ctk.CTkEntry(in_row, font=FONT_SMALL)
        self.input_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(in_row, text="浏览", command=self._browse_input,
                     width=60, font=FONT_SMALL, height=28).pack(side="right", padx=(8, 0))

        # 模板影像（仅匹配模式）
        self.template_label = ctk.CTkLabel(self, text="模板影像", font=FONT_NORMAL)
        self.template_row = ctk.CTkFrame(self, fg_color="transparent")
        self.template_entry = ctk.CTkEntry(self.template_row, font=FONT_SMALL)
        ctk.CTkButton(self.template_row, text="浏览", command=self._browse_template,
                     width=60, font=FONT_SMALL, height=28)

        # 输出目录
        ctk.CTkLabel(self, text="输出目录", font=FONT_NORMAL).pack(anchor="w", padx=20, pady=(12, 2))
        out_row = ctk.CTkFrame(self, fg_color="transparent")
        out_row.pack(fill="x", padx=20)
        self.output_entry = ctk.CTkEntry(out_row, font=FONT_SMALL)
        self.output_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(out_row, text="浏览", command=self._browse_output,
                     width=60, font=FONT_SMALL, height=28).pack(side="right", padx=(8, 0))

        # 子目录递归
        self.recursive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="包含子目录", variable=self.recursive_var,
                       font=FONT_SMALL).pack(anchor="w", padx=20, pady=(10, 5))

        # 进度
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=20, pady=(10, 2))
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(self, text="", font=FONT_SMALL,
                                          text_color=THEME["text_secondary"])
        self.progress_label.pack()

        # 执行按钮
        ctk.CTkButton(self, text="开始处理", command=self._start_batch,
                     fg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                     font=FONT_NORMAL, height=36, corner_radius=8).pack(pady=15)

        self._on_type_change()

    def _on_type_change(self):
        is_match = self.task_type.get() == "match"
        if is_match:
            self.template_label.pack(anchor="w", padx=20, pady=(10, 2))
            self.template_row.pack(fill="x", padx=20)
            self.template_entry.pack(side="left", fill="x", expand=True)
            self.template_row.winfo_children()[1].pack(side="right", padx=(8, 0))
        else:
            self.template_label.pack_forget()
            self.template_row.pack_forget()

    def _browse_input(self):
        d = filedialog.askdirectory(title="选择输入目录")
        if d:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, d)

    def _browse_template(self):
        f = filedialog.askopenfilename(title="选择模板影像",
                                       filetypes=[("影像文件", "*.png *.jpg *.tif *.tiff *.bmp")])
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
        self.progress.set(0)
        self.progress_label.configure(text="正在收集影像文件...")

        def run():
            try:
                if self.task_type.get() == "feature":
                    self.result = self.processor.batch_feature_detect(
                        input_dir, output_dir, recursive=recursive
                    )
                else:
                    template = self.template_entry.get().strip()
                    if not template or not os.path.isfile(template):
                        self.after(0, lambda: messagebox.showerror("错误", "请选择模板影像"))
                        return
                    self.result = self.processor.batch_match(
                        template, input_dir, output_dir, recursive=recursive
                    )

                self.after(0, self._on_complete)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("错误", str(e)))

        self.processor.on_progress(lambda c, t, m: self.after(0, self._update_progress, c, t, m))
        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, current, total, message):
        self.progress.set(current / total if total > 0 else 0)
        self.progress_label.configure(text=f"{current}/{total} - {message}")

    def _on_complete(self):
        if self.result and self.result.total > 0:
            msg = (
                f"批量处理完成！\n\n"
                f"总数: {self.result.total}\n"
                f"成功: {self.result.success}\n"
                f"失败: {self.result.failed}\n"
                f"成功率: {self.result.success_rate:.1f}%\n"
                f"耗时: {self.result.elapsed:.1f} 秒"
            )
            messagebox.showinfo("完成", msg)
            self.destroy()
        else:
            messagebox.showwarning("提示", "未找到任何可处理的影像文件")
