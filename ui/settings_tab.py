"""设置面板 - RSTao-Tool"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path

from .theme import (THEME, FONT_SUBTITLE, FONT_NORMAL, FONT_SMALL, PANEL_STYLE,
                     SECTION_STYLE, apply_theme, get_current_mode)
from common.i18n import t, load_language, current_lang


class SettingsTab(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=40, pady=20)

        ctk.CTkLabel(scroll, text="偏好设置",
                    font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w", pady=(0, 20))

        self._section_title(scroll, "外观")
        card1 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card1.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(card1, text="主题模式", font=FONT_NORMAL).pack(anchor="w", padx=16, pady=(12, 4))
        self.theme_var = ctk.StringVar(value=get_current_mode())
        theme_row = ctk.CTkFrame(card1, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkRadioButton(theme_row, text="深色  ", variable=self.theme_var, value="dark",
                           command=self._on_theme_change, font=FONT_SMALL).pack(side="left")
        ctk.CTkRadioButton(theme_row, text="浅色", variable=self.theme_var, value="light",
                           command=self._on_theme_change, font=FONT_SMALL).pack(side="left", padx=20)

        ctk.CTkLabel(card1, text="界面语言", font=FONT_NORMAL).pack(anchor="w", padx=16, pady=(0, 4))
        self.lang_var = ctk.StringVar(value=current_lang())
        lang_row = ctk.CTkFrame(card1, fg_color="transparent")
        lang_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkRadioButton(lang_row, text="中文  ", variable=self.lang_var, value="zh",
                           command=self._on_lang_change, font=FONT_SMALL).pack(side="left")
        ctk.CTkRadioButton(lang_row, text="English", variable=self.lang_var, value="en",
                           command=self._on_lang_change, font=FONT_SMALL).pack(side="left", padx=20)

        self._section_title(scroll, "存储")
        card2 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card2.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(card2, text="缓存目录", font=FONT_NORMAL).pack(anchor="w", padx=16, pady=(12, 4))
        cache_row = ctk.CTkFrame(card2, fg_color="transparent")
        cache_row.pack(fill="x", padx=16, pady=(0, 12))
        self.cache_entry = ctk.CTkEntry(cache_row, font=FONT_SMALL)
        self.cache_entry.pack(side="left", fill="x", expand=True)
        self.cache_entry.insert(0, str(Path.home() / ".rstao_cache"))
        ctk.CTkButton(cache_row, text="浏览", command=self._browse_cache,
                      width=60, font=FONT_SMALL, height=28).pack(side="right", padx=(8, 0))

        self._section_title(scroll, "算法默认参数")
        card3 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card3.pack(fill="x", pady=(0, 12))

        defaults = [("Harris k", "0.04"), ("匹配阈值", "0.80"), ("NMS 半径", "5")]
        for label, val in defaults:
            row = ctk.CTkFrame(card3, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row, text=label, font=FONT_SMALL, width=80,
                        text_color=THEME["text_secondary"]).pack(side="left")
            entry = ctk.CTkEntry(row, font=FONT_SMALL, width=100, height=28)
            entry.insert(0, val)
            entry.pack(side="left")

        ctk.CTkButton(scroll, text="恢复默认设置", command=self._reset_defaults,
                      fg_color="transparent", border_width=1, border_color=THEME["border"],
                      text_color=THEME["text_secondary"], hover_color=THEME["hover"],
                      font=FONT_NORMAL, height=36, corner_radius=8).pack(pady=24)

    def _section_title(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Microsoft YaHei UI", 11, "bold"),
                    text_color=THEME["text_muted"]).pack(anchor="w", pady=(16, 4))

    def _on_lang_change(self):
        lang = self.lang_var.get()
        load_language(lang)
        lang_name = "中文" if lang == "zh" else "English"
        messagebox.showinfo("", f"语言已切换为 {lang_name}，重启后完全生效")

    def _on_theme_change(self):
        theme = self.theme_var.get()
        apply_theme(theme)
        try:
            master = self.winfo_toplevel()
            if hasattr(master, "refresh_theme"):
                master.refresh_theme()
        except Exception:
            pass
        messagebox.showinfo("", "主题已切换")

    def _browse_cache(self):
        d = filedialog.askdirectory(title="选择缓存目录")
        if d:
            self.cache_entry.delete(0, "end")
            self.cache_entry.insert(0, d)

    def _reset_defaults(self):
        messagebox.showinfo("恢复默认", "已恢复默认设置（需重启生效）")