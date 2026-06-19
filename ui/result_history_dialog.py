"""Project result/task history viewer."""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from .theme import FONT_NORMAL, FONT_SMALL, PANEL_STYLE, THEME
from .ui_helpers import make_button, notify


class ResultHistoryDialog(ctk.CTkToplevel):
    """Show saved project result and task records."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.project_manager = getattr(parent, "project_manager", None)
        self.records = []

        self.title("结果历史")
        self.geometry("820x520")
        self.minsize(720, 440)
        self.configure(fg_color=THEME["bg"])

        self._create_ui()
        self.refresh()
        self.focus()

    def _create_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="结果历史", font=("Microsoft YaHei UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        make_button(header, "刷新", self.refresh, "secondary", height=30).grid(
            row=0, column=1, padx=(8, 0)
        )
        make_button(header, "复制输出路径", self.copy_selected_output, "secondary", height=30).grid(
            row=0, column=2, padx=(8, 0)
        )
        make_button(
            header, "打开输出位置", self.open_selected_output_dir, "secondary", height=30
        ).grid(row=0, column=3, padx=(8, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        table_wrap = ctk.CTkFrame(body, **PANEL_STYLE)
        table_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)

        columns = ("created_at", "category", "title", "status")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("created_at", text="时间")
        self.tree.heading("category", text="类型")
        self.tree.heading("title", text="名称")
        self.tree.heading("status", text="状态")
        self.tree.column("created_at", width=150, anchor="w")
        self.tree.column("category", width=90, anchor="w")
        self.tree.column("title", width=260, anchor="w")
        self.tree.column("status", width=70, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_wrap = ctk.CTkFrame(body, **PANEL_STYLE)
        detail_wrap.grid(row=0, column=1, sticky="nsew")
        detail_wrap.grid_rowconfigure(1, weight=1)
        detail_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(detail_wrap, text="详情", font=FONT_NORMAL).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4)
        )
        self.detail_text = ctk.CTkTextbox(
            detail_wrap, font=("Consolas", 10), fg_color=THEME["card"]
        )
        self.detail_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        project = (
            getattr(self.project_manager, "current_project", None) if self.project_manager else None
        )
        if not project:
            self.records = []
            self._set_detail("当前没有打开项目。")
            return

        results = list(project.get("result_history", []))
        tasks = list(project.get("task_history", []))
        self.records = sorted(
            results + tasks,
            key=lambda r: r.get("created_at", ""),
            reverse=True,
        )

        for idx, record in enumerate(self.records):
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    record.get("created_at", ""),
                    record.get("category", ""),
                    record.get("title", ""),
                    record.get("status", ""),
                ),
            )

        if self.records:
            self.tree.selection_set("0")
            self._show_record(self.records[0])
        else:
            self._set_detail("还没有结果记录。导出、检测或批处理完成后会自动写入这里。")

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        if 0 <= idx < len(self.records):
            self._show_record(self.records[idx])

    def _show_record(self, record):
        lines = [
            f"时间: {record.get('created_at', '')}",
            f"类型: {record.get('category', '')}",
            f"名称: {record.get('title', '')}",
            f"状态: {record.get('status', '')}",
            "",
            "输入:",
            *[f"  {p}" for p in record.get("inputs", [])],
            "",
            "输出:",
            *[f"  {p}" for p in record.get("outputs", [])],
            "",
            "参数:",
            json.dumps(record.get("params", {}), ensure_ascii=False, indent=2),
            "",
            "指标:",
            json.dumps(record.get("metrics", {}), ensure_ascii=False, indent=2),
        ]
        notes = record.get("notes", "")
        if notes:
            lines.extend(["", "备注:", notes])
        self._set_detail("\n".join(lines))

    def _set_detail(self, text):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _selected_record(self):
        selection = self.tree.selection()
        if not selection:
            return None
        idx = int(selection[0])
        return self.records[idx] if 0 <= idx < len(self.records) else None

    def _first_existing_output(self):
        record = self._selected_record()
        if not record:
            return ""
        for output in record.get("outputs", []):
            if output and os.path.exists(output):
                return output
        outputs = record.get("outputs", [])
        return outputs[0] if outputs else ""

    def copy_selected_output(self):
        output = self._first_existing_output()
        if not output:
            messagebox.showwarning("提示", "当前记录没有输出路径。")
            return
        self.clipboard_clear()
        self.clipboard_append(output)
        notify(self, "输出路径已复制", "success")

    def open_selected_output_dir(self):
        output = self._first_existing_output()
        if not output:
            messagebox.showwarning("提示", "当前记录没有输出路径。")
            return
        folder = output if os.path.isdir(output) else os.path.dirname(output)
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("提示", "输出位置不存在。")
            return
        try:
            os.startfile(folder)
        except OSError as exc:
            messagebox.showerror("错误", f"无法打开输出位置: {exc}")
