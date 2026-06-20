"""Import preflight preview dialog."""

from __future__ import annotations

import customtkinter as ctk

from core.input_inspector import InspectionResult, inspect_file

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, THEME


class ImportPreviewDialog(ctk.CTkToplevel):
    """Small modal preview shown before importing external files."""

    def __init__(self, parent, result: InspectionResult):
        super().__init__(parent)
        self.result = result
        self.confirmed = False
        self.title(result.title)
        self.geometry("560x520")
        self.minsize(520, 420)
        self.configure(fg_color=THEME["bg"])
        self.transient(parent)
        self.grab_set()
        self._build()
        self.after(50, self.focus)

    def _build(self):
        ctk.CTkLabel(
            self,
            text=self.result.title,
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=THEME["text_primary"],
        ).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            self,
            text=self.result.path,
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        body = ctk.CTkScrollableFrame(self, fg_color=THEME["card"], corner_radius=8)
        body.pack(fill="both", expand=True, padx=20, pady=8)

        for key, value in self.result.summary:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=key, width=86, anchor="w", font=FONT_SMALL).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                anchor="w",
                font=FONT_SMALL,
                text_color=THEME["text_secondary"],
                wraplength=360,
                justify="left",
            ).pack(side="left", fill="x", expand=True)

        if self.result.warnings:
            ctk.CTkLabel(body, text="注意", font=FONT_SUBTITLE, text_color=THEME["warning"]).pack(
                anchor="w", padx=10, pady=(12, 4)
            )
            for warning in self.result.warnings:
                ctk.CTkLabel(
                    body,
                    text=warning,
                    font=FONT_SMALL,
                    text_color=THEME["warning"],
                    wraplength=470,
                    justify="left",
                ).pack(anchor="w", padx=10, pady=2)

        if self.result.preview_rows:
            ctk.CTkLabel(body, text="前几行", font=FONT_SUBTITLE).pack(
                anchor="w", padx=10, pady=(12, 4)
            )
            for row in self.result.preview_rows[:5]:
                ctk.CTkLabel(
                    body,
                    text=" | ".join(row),
                    font=("Consolas", 10),
                    text_color=THEME["text_secondary"],
                    wraplength=470,
                    justify="left",
                ).pack(anchor="w", padx=10, pady=2)

        if self.result.message:
            ctk.CTkLabel(
                body,
                text=self.result.message,
                font=FONT_NORMAL,
                text_color=THEME["danger"] if not self.result.can_import else THEME["text_primary"],
                wraplength=470,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(12, 4))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(8, 18))
        ctk.CTkButton(
            buttons,
            text="取消",
            width=96,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
            command=self._cancel,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            buttons,
            text="继续导入" if self.result.can_import else "无法导入",
            width=120,
            state=ctk.NORMAL if self.result.can_import else ctk.DISABLED,
            command=self._confirm,
        ).pack(side="right", padx=4)

    def _confirm(self):
        self.confirmed = True
        self.destroy()

    def _cancel(self):
        self.confirmed = False
        self.destroy()


def confirm_import(parent, path: str, expected_kind: str | None = None) -> bool:
    """Inspect a file and ask the user before import."""
    result = inspect_file(path, expected_kind)
    dialog = ImportPreviewDialog(parent, result)
    parent.wait_window(dialog)
    return bool(dialog.confirmed)
