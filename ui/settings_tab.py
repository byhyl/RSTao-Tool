"""设置面板"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path

from .theme import THEME, FONT_SUBTITLE, FONT_NORMAL, FONT_SMALL, PANEL_STYLE
from common.i18n import t, load_language, current_lang


class SettingsTab(ctk.CTkFrame):
    """设置标签页"""

    def __init__(self, parent):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=30, pady=20)

        # === 语言 ===
        ctk.CTkLabel(scroll, text="界面语言 / Language", font=FONT_SUBTITLE).pack(anchor="w", pady=(15, 5))
        lang_frame = ctk.CTkFrame(scroll, **PANEL_STYLE)
        lang_frame.pack(fill="x", pady=5)
        self.lang_var = ctk.StringVar(value=current_lang())
        ctk.CTkRadioButton(lang_frame, text="中文", variable=self.lang_var, value="zh",
                           command=self._on_lang_change, font=FONT_NORMAL).pack(side="left", padx=15, pady=10)
        ctk.CTkRadioButton(lang_frame, text="English", variable=self.lang_var, value="en",
                           command=self._on_lang_change, font=FONT_NORMAL).pack(side="left", padx=15, pady=10)

        # === 主题 ===
        ctk.CTkLabel(scroll, text="主题 / Theme", font=FONT_SUBTITLE).pack(anchor="w", pady=(15, 5))
        theme_frame = ctk.CTkFrame(scroll, **PANEL_STYLE)
        theme_frame.pack(fill="x", pady=5)
        self.theme_var = ctk.StringVar(value="dark")
        ctk.CTkRadioButton(theme_frame, text="深色 Dark", variable=self.theme_var, value="dark",
                           command=self._on_theme_change, font=FONT_NORMAL).pack(side="left", padx=15, pady=10)
        ctk.CTkRadioButton(theme_frame, text="浅色 Light", variable=self.theme_var, value="light",
                           command=self._on_theme_change, font=FONT_NORMAL).pack(side="left", padx=15, pady=10)

        # === 缓存目录 ===
        ctk.CTkLabel(scroll, text="缓存目录 / Cache", font=FONT_SUBTITLE).pack(anchor="w", pady=(15, 5))
        cache_frame = ctk.CTkFrame(scroll, **PANEL_STYLE)
        cache_frame.pack(fill="x", pady=5)
        self.cache_entry = ctk.CTkEntry(cache_frame, font=FONT_SMALL)
        self.cache_entry.pack(side="left", fill="x", expand=True, padx=(15, 5), pady=10)
        self.cache_entry.insert(0, str(Path.home() / ".rstao_cache"))
        ctk.CTkButton(cache_frame, text="浏览", command=self._browse_cache, width=60,
                      font=FONT_SMALL).pack(side="right", padx=15, pady=10)

        # === 默认参数 ===
        ctk.CTkLabel(scroll, text="默认参数 / Defaults", font=FONT_SUBTITLE).pack(anchor="w", pady=(15, 5))
        param_frame = ctk.CTkFrame(scroll, **PANEL_STYLE)
        param_frame.pack(fill="x", pady=5)

        for label, val in [("Harris k", "0.04"), ("匹配阈值", "0.80"), ("NMS 半径", "5")]:
            row = ctk.CTkFrame(param_frame, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=5)
            ctk.CTkLabel(row, text=f"{label}:", font=FONT_NORMAL, width=90).pack(side="left")
            entry = ctk.CTkEntry(row, font=FONT_SMALL, width=80)
            entry.insert(0, val)
            entry.pack(side="left")

        ctk.CTkButton(scroll, text="恢复默认设置", command=self._reset_defaults,
                      fg_color="transparent", border_width=1, border_color=THEME["border"],
                      font=FONT_NORMAL, height=36).pack(pady=20)

    def _on_lang_change(self):
        lang = self.lang_var.get()
        load_language(lang)
        messagebox.showinfo("", f"语言已切换为 {'中文' if lang == 'zh' else 'English'}，重启后完全生效")

    def _on_theme_change(self):
        theme = self.theme_var.get()
        ctk.set_appearance_mode("Dark" if theme == "dark" else "Light")
        messagebox.showinfo("", "主题已切换")

    def _browse_cache(self):
        d = filedialog.askdirectory(title="选择缓存目录")
        if d:
            self.cache_entry.delete(0, "end")
            self.cache_entry.insert(0, d)

    def _reset_defaults(self):
        messagebox.showinfo("恢复默认", "已恢复默认设置（需重启生效）")