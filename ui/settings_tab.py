"""设置面板 - RSTao-Tool（支持持久化）"""

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from common.i18n import current_lang, load_language, t

from .settings_manager import load_settings, save_settings
from .theme import (
    FONT_NORMAL,
    FONT_SMALL,
    FONT_SUBTITLE,
    PANEL_STYLE,
    SECTION_STYLE,
    THEME,
    apply_theme,
    get_current_mode,
)
from .ui_helpers import notify


class SettingsTab(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=THEME["bg"])
        self.parent = parent
        self._settings = load_settings()
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=40, pady=20)

        ctk.CTkLabel(
            scroll,
            text=t("settings.title", t("settings.title", "偏好设置")),
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w", pady=(0, 20))

        # ---- 外观 ----
        self._section_title(scroll, t("settings.appearance", "外观"))
        card1 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card1.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(card1, text=t("settings.theme", "主题模式"), font=FONT_NORMAL).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        self.theme_var = ctk.StringVar(value=self._settings.get("theme", get_current_mode()))
        theme_row = ctk.CTkFrame(card1, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkRadioButton(
            theme_row,
            text="深色  ",
            variable=self.theme_var,
            value="dark",
            command=self._on_theme_change,
            font=FONT_SMALL,
        ).pack(side="left")
        ctk.CTkRadioButton(
            theme_row,
            text="浅色",
            variable=self.theme_var,
            value="light",
            command=self._on_theme_change,
            font=FONT_SMALL,
        ).pack(side="left", padx=20)

        ctk.CTkLabel(card1, text=t("settings.language", "界面语言"), font=FONT_NORMAL).pack(
            anchor="w", padx=16, pady=(0, 4)
        )
        self.lang_var = ctk.StringVar(value=self._settings.get("language", current_lang()))
        lang_row = ctk.CTkFrame(card1, fg_color="transparent")
        lang_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkRadioButton(
            lang_row,
            text="中文  ",
            variable=self.lang_var,
            value="zh",
            command=self._on_lang_change,
            font=FONT_SMALL,
        ).pack(side="left")
        ctk.CTkRadioButton(
            lang_row,
            text="English",
            variable=self.lang_var,
            value="en",
            command=self._on_lang_change,
            font=FONT_SMALL,
        ).pack(side="left", padx=20)

        # ---- 存储 ----
        self._section_title(scroll, t("settings.storage", "存储"))
        card2 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card2.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(card2, text=t("settings.cache", "缓存目录"), font=FONT_NORMAL).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        cache_row = ctk.CTkFrame(card2, fg_color="transparent")
        cache_row.pack(fill="x", padx=16, pady=(0, 12))
        self.cache_entry = ctk.CTkEntry(cache_row, font=FONT_SMALL)
        self.cache_entry.pack(side="left", fill="x", expand=True)
        self.cache_entry.insert(
            0, self._settings.get("cache_dir", str(Path.home() / ".rstao_cache"))
        )
        ctk.CTkButton(
            cache_row,
            text=t("common.browse", "浏览"),
            command=self._browse_cache,
            width=60,
            font=FONT_SMALL,
            height=28,
        ).pack(side="right", padx=(8, 0))

        # ---- 算法默认参数 ----
        self._section_title(scroll, t("settings.defaults", "默认参数"))
        card3 = ctk.CTkFrame(scroll, **SECTION_STYLE)
        card3.pack(fill="x", pady=(0, 12))

        defaults_data = self._settings.get("defaults", {})
        defaults = [
            ("Harris k", "harris_k", str(defaults_data.get("harris_k", 0.04))),
            ("SUSAN T", "susan_t", str(defaults_data.get("susan_t", 25))),
            (
                t("feature.point_size", "特征点大小"),
                "point_size",
                str(defaults_data.get("point_size", 4)),
            ),
            (
                t("settings.match_threshold", "匹配阈值"),
                "match_threshold",
                str(defaults_data.get("match_threshold", 0.80)),
            ),
            (
                t("settings.nms_radius", "NMS 半径"),
                "nms_radius",
                str(defaults_data.get("nms_radius", 5)),
            ),
            (
                t("detect.confidence", "置信度阈值"),
                "confidence",
                str(defaults_data.get("confidence", 0.50)),
            ),
            (
                t("detect.iou", "IOU 阈值"),
                "iou_threshold",
                str(defaults_data.get("iou_threshold", 0.45)),
            ),
        ]
        self._default_entries = {}
        for label, key, val in defaults:
            row = ctk.CTkFrame(card3, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(
                row, text=label, font=FONT_SMALL, width=80, text_color=THEME["text_secondary"]
            ).pack(side="left")
            entry = ctk.CTkEntry(row, font=FONT_SMALL, width=100, height=28)
            entry.insert(0, val)
            entry.pack(side="left")
            self._default_entries[key] = entry

        # ---- 按钮 ----
        ctk.CTkButton(
            scroll,
            text=t("settings.reset", "恢复默认设置"),
            command=self._reset_defaults,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_secondary"],
            hover_color=THEME["hover"],
            font=FONT_NORMAL,
            height=36,
            corner_radius=8,
        ).pack(pady=24)

        # 保存按钮
        ctk.CTkButton(
            scroll,
            text=t("common.save", "保存设置"),
            command=self._save_all,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            font=FONT_NORMAL,
            height=36,
            corner_radius=8,
        ).pack(pady=(0, 10))

    def _section_title(self, parent, text):
        ctk.CTkLabel(
            parent,
            text=text,
            font=("Microsoft YaHei UI", 11, "bold"),
            text_color=THEME["text_muted"],
        ).pack(anchor="w", pady=(16, 4))

    def _on_lang_change(self):
        lang = self.lang_var.get()
        load_language(lang)
        self._settings["language"] = lang
        save_settings(self._settings)
        lang_name = "中文" if lang == "zh" else "English"
        notify(
            self,
            f"{t('settings.lang_changed', '语言已切换为')} {lang_name}，重新进入界面后完全生效",
            "success",
        )

    def _on_theme_change(self):
        theme = self.theme_var.get()
        apply_theme(theme)
        self._settings["theme"] = theme
        save_settings(self._settings)
        try:
            master = self.winfo_toplevel()
            if hasattr(master, "refresh_theme"):
                master.refresh_theme()
            # Force refresh all descendant widgets
            for child in master.winfo_children():
                try:
                    child.configure(fg_color=THEME["bg"])
                except Exception:
                    pass
            master.update_idletasks()
        except Exception:
            pass

    def _browse_cache(self):
        d = filedialog.askdirectory(title="选择缓存目录")
        if d:
            self.cache_entry.delete(0, "end")
            self.cache_entry.insert(0, d)
            self._settings["cache_dir"] = d
            save_settings(self._settings)

    def _reset_defaults(self):
        from .settings_manager import DEFAULT_SETTINGS

        self._settings = dict(DEFAULT_SETTINGS)
        save_settings(self._settings)
        defaults = self._settings.get("defaults", {})
        for key, entry in getattr(self, "_default_entries", {}).items():
            entry.delete(0, "end")
            entry.insert(0, str(defaults.get(key, "")))
        self.cache_entry.delete(0, "end")
        self.cache_entry.insert(
            0, self._settings.get("cache_dir", str(Path.home() / ".rstao_cache"))
        )
        self.theme_var.set(self._settings.get("theme", get_current_mode()))
        self.lang_var.set(self._settings.get("language", current_lang()))
        notify(self, t("settings.reset_done", "已恢复默认设置"), "success")

    def _save_all(self):
        # 读取当前 UI 中的算法参数
        defaults = {}
        for key, entry in self._default_entries.items():
            try:
                defaults[key] = float(entry.get().strip())
            except ValueError:
                defaults[key] = self._settings["defaults"].get(key, 0)
        self._settings["defaults"] = defaults
        self._settings["cache_dir"] = self.cache_entry.get().strip()
        save_settings(self._settings)
        notify(self, t("settings.saved", "设置已保存"), "success")

    def get_state(self):
        settings = dict(self._settings)
        settings["theme"] = self.theme_var.get()
        settings["language"] = self.lang_var.get()
        settings["cache_dir"] = self.cache_entry.get().strip()

        defaults = dict(settings.get("defaults", {}))
        for key, entry in getattr(self, "_default_entries", {}).items():
            raw = entry.get().strip()
            try:
                defaults[key] = float(raw)
            except ValueError:
                defaults[key] = raw
        settings["defaults"] = defaults
        return settings

    def set_state(self, state):
        if not state:
            return

        self._settings.update(state)
        self.theme_var.set(self._settings.get("theme", get_current_mode()))
        self.lang_var.set(self._settings.get("language", current_lang()))
        self.cache_entry.delete(0, "end")
        self.cache_entry.insert(
            0, self._settings.get("cache_dir", str(Path.home() / ".rstao_cache"))
        )

        defaults = self._settings.get("defaults", {})
        for key, entry in getattr(self, "_default_entries", {}).items():
            if key in defaults:
                entry.delete(0, "end")
                entry.insert(0, str(defaults[key]))
