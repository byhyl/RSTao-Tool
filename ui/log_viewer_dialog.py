"""Runtime log viewer."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from common.config import APP_NAME, LOG_DIR

from .theme import FONT_NORMAL, PANEL_STYLE, THEME
from .ui_helpers import make_button, notify


class LogViewerDialog(ctk.CTkToplevel):
    """Show the tail of the application log file."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.log_path = Path(LOG_DIR) / f"{APP_NAME}.log"

        self.title("运行日志")
        self.geometry("860x560")
        self.minsize(720, 420)
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
        ctk.CTkLabel(header, text="运行日志", font=("Microsoft YaHei UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header, text=str(self.log_path), font=("Consolas", 10), text_color=THEME["text_muted"]
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        make_button(header, "刷新", self.refresh, "secondary", height=30).grid(
            row=0, column=1, rowspan=2, padx=(8, 0)
        )
        make_button(header, "复制", self.copy_log, "secondary", height=30).grid(
            row=0, column=2, rowspan=2, padx=(8, 0)
        )

        body = ctk.CTkFrame(self, **PANEL_STYLE)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(
            body, font=("Consolas", 10), fg_color=THEME["card"], wrap="none"
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def refresh(self):
        content = self._read_tail()
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", content)
        self.textbox.configure(state="disabled")
        self.textbox.see("end")

    def copy_log(self):
        content = self.textbox.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("提示", "当前没有可复制的日志。")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        notify(self, "日志内容已复制", "success")

    def _read_tail(self, max_lines: int = 600) -> str:
        if not self.log_path.exists():
            return "日志文件尚未生成。"
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            tail = lines[-max_lines:]
            return "".join(tail).strip() or "日志文件为空。"
        except OSError as exc:
            return f"读取日志失败: {exc}"
