"""Actionable error dialog helpers."""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
import pyperclip

from common.config import LOG_DIR

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, THEME


def show_actionable_error(
    parent,
    title: str,
    message: str,
    suggestion: str = "",
    detail: str = "",
    log_path: str | Path | None = None,
):
    """Show an error with a user-facing next step and optional technical detail."""
    if parent is None:
        messagebox.showerror(title, f"{message}\n\n{suggestion}".strip())
        return

    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("520x360")
    dialog.configure(fg_color=THEME["bg"])
    dialog.transient(parent)
    dialog.grab_set()

    ctk.CTkLabel(
        dialog, text=title, font=("Microsoft YaHei UI", 18, "bold"), text_color=THEME["danger"]
    ).pack(anchor="w", padx=20, pady=(18, 6))
    ctk.CTkLabel(
        dialog,
        text=message,
        font=FONT_NORMAL,
        wraplength=470,
        justify="left",
        text_color=THEME["text_primary"],
    ).pack(anchor="w", padx=20, pady=4)
    if suggestion:
        ctk.CTkLabel(
            dialog,
            text=suggestion,
            font=FONT_SMALL,
            wraplength=470,
            justify="left",
            text_color=THEME["warning"],
        ).pack(anchor="w", padx=20, pady=(4, 10))

    detail_box = ctk.CTkTextbox(dialog, height=96, wrap="word", font=("Consolas", 10))
    detail_box.pack(fill="both", expand=True, padx=20, pady=8)
    detail_text = detail or message
    detail_box.insert("end", detail_text)
    detail_box.configure(state="disabled")

    buttons = ctk.CTkFrame(dialog, fg_color="transparent")
    buttons.pack(fill="x", padx=20, pady=(4, 18))

    def copy_detail():
        pyperclip.copy(detail_text)

    def open_log():
        target = Path(log_path) if log_path else LOG_DIR
        if target.exists():
            os.startfile(str(target))

    ctk.CTkButton(buttons, text="关闭", width=80, command=dialog.destroy).pack(side="right", padx=4)
    ctk.CTkButton(buttons, text="复制错误", width=92, command=copy_detail).pack(
        side="right", padx=4
    )
    ctk.CTkButton(
        buttons,
        text="打开日志",
        width=92,
        fg_color="transparent",
        border_width=1,
        border_color=THEME["border"],
        text_color=THEME["text_primary"],
        command=open_log,
    ).pack(side="right", padx=4)

    dialog.after(50, dialog.focus)
