"""设置面板"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path

from .theme import THEME, FONT_SUBTITLE, FONT_NORMAL, FONT_SMALL, CollapsibleCard
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
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # 语言设置
        self.lang_card = CollapsibleCard(scroll, t("settings.language"))
        self.lang_card.pack(fill="x", pady=5)

        row = ctk.CTkFrame(self.lang_card.content, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=10)
        self.lang_var = ctk.StringVar(value=current_lang())
        ctk.CTkRadioButton(row, text="中文", variable=self.lang_var, value="zh",
                           command=self._on_lang_change, font=FONT_NORMAL).pack(side="left", padx=10)
        ctk.CTkRadioButton(row, text="English", variable=self.lang_var, value="en",
                           command=self._on_lang_change, font=FONT_NORMAL).pack(side="left", padx=10)

        # 主题设置
        self.theme_card = CollapsibleCard(scroll, t("settings.theme"))
        self.theme_card.pack(fill="x", pady=5)

        trow = ctk.CTkFrame(self.theme_card.content, fg_color="transparent")
        trow.pack(fill="x", padx=10, pady=10)
        self.theme_var = ctk.StringVar(value="dark")
        ctk.CTkRadioButton(trow, text="深色", variable=self.theme_var, value="dark",
                           command=self._on_theme_change, font=FONT_NORMAL).pack(side="left", padx=10)
        ctk.CTkRadioButton(trow, text="浅色", variable=self.theme_var, value="light",
                           command=self._on_theme_change, font=FONT_NORMAL).pack(side="left", padx=10)

        # 缓存目录
        self.cache_card = CollapsibleCard(scroll, t("settings.cache"))
        self.cache_card.pack(fill="x", pady=5)

        crow = ctk.CTkFrame(self.cache_card.content, fg_color="transparent")
        crow.pack(fill="x", padx=10, pady=10)
        self.cache_entry = ctk.CTkEntry(crow, font=FONT_SMALL)
        self.cache_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.cache_entry.insert(0, str(Path.home() / ".rstao_cache"))
        ctk.CTkButton(crow, text="浏览", command=self._browse_cache, width=60,
                      font=FONT_SMALL).pack(side="right")

        # 默认参数
        self.defaults_card = CollapsibleCard(scroll, t("settings.defaults"))
        self.defaults_card.pack(fill="x", pady=5)

        self._add_param_row("Harris k:", "0.04")
        self._add_param_row("匹配阈值:", "0.80")
        self._add_param_row("NMS 半径:", "5")

        ctk.CTkButton(scroll, text=t("settings.reset"), command=self._reset_defaults,
                      fg_color="transparent", border_width=1, border_color=THEME["border"],
                      font=FONT_NORMAL).pack(pady=15)

    def _add_param_row(self, label, default_val):
        row = ctk.CTkFrame(self.defaults_card.content, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(row, text=label, font=FONT_SMALL, width=80).pack(side="left")
        entry = ctk.CTkEntry(row, font=FONT_SMALL, width=100)
        entry.insert(0, default_val)
        entry.pack(side="left")

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
        messagebox.showinfo(t("settings.reset"), "已恢复默认设置（需重启生效）")