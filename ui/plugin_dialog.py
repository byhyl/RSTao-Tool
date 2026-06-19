"""插件管理对话框"""

from tkinter import messagebox

import customtkinter as ctk

from core.plugin_manager import PluginInfo, PluginManager

from .theme import FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, SECTION_STYLE, THEME


class PluginDialog(ctk.CTkToplevel):
    """插件管理窗口"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("插件管理")
        self.geometry("500x420")
        self.resizable(False, False)
        self.configure(fg_color=THEME["bg"])
        self._pm = PluginManager()
        self._create_ui()
        self._refresh_list()
        self.focus()
        self.grab_set()

    def _create_ui(self):
        ctk.CTkLabel(self, text="插件管理", font=("Microsoft YaHei UI", 18, "bold")).pack(
            pady=(16, 4)
        )
        ctk.CTkLabel(
            self, text="已安装的扩展插件", font=FONT_SMALL, text_color=THEME["text_secondary"]
        ).pack(pady=(0, 10))

        self.plugin_list = ctk.CTkScrollableFrame(
            self, height=220, fg_color=THEME["card"], corner_radius=8
        )
        self.plugin_list.pack(fill="x", padx=20, pady=5)

        info_card = ctk.CTkFrame(self, **SECTION_STYLE)
        info_card.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(
            info_card,
            text="安装插件: 在 plugins/ 下创建子文件夹，放入 plugin.json + Python 模块即可",
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
        ).pack(padx=14, pady=10)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(
            btn_row, text="刷新列表", command=self._refresh_list, width=90, font=FONT_SMALL
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row,
            text="打开插件目录",
            command=self._open_dir,
            width=110,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
        ).pack(side="left", padx=4)

    def _refresh_list(self):
        for w in self.plugin_list.winfo_children():
            w.destroy()
        plugins = self._pm.discover()
        if not plugins:
            ctk.CTkLabel(
                self.plugin_list, text="暂无插件", font=FONT_NORMAL, text_color=THEME["text_muted"]
            ).pack(pady=30)
            return
        for p in plugins:
            row = ctk.CTkFrame(self.plugin_list, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(row, text=p.name, font=FONT_NORMAL).pack(side="left", padx=4)
            ctk.CTkLabel(
                row, text=f"v{p.version}", font=FONT_SMALL, text_color=THEME["text_muted"]
            ).pack(side="left", padx=4)
            status = "已启用" if p.enabled else "已禁用"
            ctk.CTkLabel(
                row,
                text=status,
                font=FONT_SMALL,
                text_color=THEME["success"] if p.enabled else THEME["danger"],
            ).pack(side="right", padx=4)

    def _open_dir(self):
        import os

        plugins_dir = os.path.join(os.path.dirname(__file__), "..", "plugins")
        os.startfile(os.path.abspath(plugins_dir))
