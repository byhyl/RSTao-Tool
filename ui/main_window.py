import logging
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image

from common.i18n import load_language, t
from common.logger import logger
from common.version import APP_AUTHOR, APP_VERSION, RELEASE_DATE
from core.project_manager import ProjectManager

from .batch_dialog import BatchDialog
from .coordinate_tab import CoordinateTab
from .detection_tab import DetectionTab
from .error_dialog import show_actionable_error

# 本地模块导入
from .feature_tab import FeatureTab
from .image_processing_tab import ImageProcessingTab
from .license_info import Config, LicenseManager
from .log_viewer_dialog import LogViewerDialog
from .match_tab import MatchTab
from .plugin_dialog import PluginDialog
from .resource_panel import ResourcePanel
from .result_history_dialog import ResultHistoryDialog
from .settings_manager import load_settings, save_settings
from .settings_tab import SettingsTab
from .theme import (
    FONT_NORMAL,
    FONT_SMALL,
    FONT_SUBTITLE,
    FONT_TITLE,
    PANEL_STYLE,
    THEME,
    apply_theme,
    get_current_mode,
    init_theme,
)
from .vector_tab import VectorTab


# ====================== 工具函数 ======================
def load_icon(icon_name: str, size: tuple[int, int] = (24, 24)) -> Optional[ctk.CTkImage]:
    try:
        base_path = (
            Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Config.ICONS_DIR.parent.parent
        )
        icon_path = base_path / "assets/icons" / f"{icon_name}.png"

        if icon_path.exists():
            return ctk.CTkImage(Image.open(icon_path), size=size)
        else:
            logger.warning(f"图标文件不存在：{icon_path}")
    except Exception as e:
        logger.warning(f"加载图标失败 {icon_name}：{str(e)}")
    return None


def _safe_path_stat(path: str | Path):
    try:
        return Path(path).stat()
    except (OSError, ValueError):
        return None


def _safe_path_exists(path: str | Path) -> bool:
    return _safe_path_stat(path) is not None


class WelcomePage(ctk.CTkFrame):
    """欢迎页 - Hero 布局"""

    def __init__(
        self,
        parent,
        new_project_callback,
        open_project_callback,
        open_recent_callback,
        remove_recent_callback,
        open_location_callback,
        prune_recent_callback,
        clear_recent_callback,
    ):
        super().__init__(parent, fg_color=THEME["bg"])
        self.new_project_callback = new_project_callback
        self.open_project_callback = open_project_callback
        self.open_recent_callback = open_recent_callback
        self.remove_recent_callback = remove_recent_callback
        self.open_location_callback = open_location_callback
        self.prune_recent_callback = prune_recent_callback
        self.clear_recent_callback = clear_recent_callback

        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.pack(pady=(54, 22))
        ctk.CTkLabel(
            hero,
            text="RSTao-Tool",
            font=("Microsoft YaHei UI", 42, "bold"),
            text_color=THEME["accent"],
        ).pack()
        ctk.CTkLabel(
            hero,
            text="Remote Sensing Tool",
            font=("Microsoft YaHei UI", 14),
            text_color=THEME["text_secondary"],
        ).pack(pady=(4, 20))
        sep = ctk.CTkFrame(hero, height=1, width=120, fg_color=THEME["border"])
        sep.pack()
        ctk.CTkLabel(
            hero,
            text=t("welcome.subtitle", "专业遥感影像处理与分析平台"),
            font=("Microsoft YaHei UI", 13),
            text_color=THEME["text_muted"],
        ).pack(pady=(16, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=20)
        bs = {"width": 200, "height": 42, "font": FONT_NORMAL, "corner_radius": 8}
        ctk.CTkButton(
            actions,
            text=t("welcome.new", t("menu.new", "新建项目")),
            image=load_icon("new", (18, 18)),
            compound="left",
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self.new_project_callback,
            **bs,
        ).pack(pady=4)
        ctk.CTkButton(
            actions,
            text=t("welcome.open", "打开已有项目"),
            image=load_icon("open", (18, 18)),
            compound="left",
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
            hover_color=THEME["hover"],
            command=self.open_project_callback,
            **bs,
        ).pack(pady=4)

        ctk.CTkLabel(
            self,
            text=t("welcome.recent", "最近打开"),
            font=("Microsoft YaHei UI", 11, "bold"),
            text_color=THEME["text_muted"],
        ).pack(pady=(34, 8))
        recent_actions = ctk.CTkFrame(self, fg_color="transparent")
        recent_actions.pack(fill="x", padx=300, pady=(0, 4))
        ctk.CTkButton(
            recent_actions,
            text="清理失效",
            width=72,
            height=24,
            font=("Microsoft YaHei UI", 10),
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_secondary"],
            command=self.prune_recent_callback,
        ).pack(side="right", padx=3)
        ctk.CTkButton(
            recent_actions,
            text="清空",
            width=54,
            height=24,
            font=("Microsoft YaHei UI", 10),
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_secondary"],
            command=self.clear_recent_callback,
        ).pack(side="right", padx=3)
        self.recent_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
            corner_radius=10,
            border_width=1,
            border_color=THEME["border"],
        )
        self.recent_frame.pack(fill="x", padx=300)
        self.update_recent_list([])

    def update_recent_list(self, recent_projects):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        display = recent_projects[: Config.RECENT_PROJECTS_MAX]
        if not display:
            ctk.CTkLabel(
                self.recent_frame,
                text=t("welcome.no_recent", "暂无最近项目"),
                font=FONT_SMALL,
                text_color=THEME["text_muted"],
            ).pack(pady=16)
            return
        for path in display:
            p = Path(path)
            stat = _safe_path_stat(p)
            exists = stat is not None
            name = p.stem[:36] + "..." if len(p.stem) > 36 else p.stem
            detail = str(p.parent)
            if exists:
                detail = f"{detail}  ·  {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}"
            row = ctk.CTkFrame(self.recent_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=5)
            text_col = THEME["text_secondary"] if exists else THEME["text_muted"]
            meta_col = THEME["text_muted"]
            text_box = ctk.CTkFrame(row, fg_color="transparent")
            text_box.pack(side="left", fill="x", expand=True, padx=6)
            ctk.CTkLabel(
                text_box, text=name, font=FONT_SMALL, anchor="w", text_color=text_col
            ).pack(fill="x")
            ctk.CTkLabel(
                text_box,
                text=detail if exists else f"{path}  ·  文件不存在",
                font=("Microsoft YaHei UI", 10),
                anchor="w",
                text_color=meta_col,
            ).pack(fill="x")
            ctk.CTkButton(
                row,
                text=t("common.load", "加载") if exists else "失效",
                width=54,
                height=26,
                font=("Microsoft YaHei UI", 10),
                fg_color="transparent",
                hover_color=THEME["hover"],
                text_color=THEME["accent"] if exists else THEME["text_muted"],
                state=ctk.NORMAL if exists else ctk.DISABLED,
                command=lambda pp=path: self.open_recent_callback(pp),
            ).pack(side="right", padx=6)
            ctk.CTkButton(
                row,
                text="位置",
                width=48,
                height=26,
                font=("Microsoft YaHei UI", 10),
                fg_color="transparent",
                hover_color=THEME["hover"],
                text_color=THEME["text_secondary"] if exists else THEME["text_muted"],
                state=ctk.NORMAL if exists else ctk.DISABLED,
                command=lambda pp=path: self.open_location_callback(pp),
            ).pack(side="right", padx=2)
            ctk.CTkButton(
                row,
                text="移除",
                width=48,
                height=26,
                font=("Microsoft YaHei UI", 10),
                fg_color="transparent",
                hover_color=THEME["hover"],
                text_color=THEME["text_muted"],
                command=lambda pp=path: self.remove_recent_callback(pp),
            ).pack(side="right", padx=2)


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        # 加载持久化设置
        self._app_settings = load_settings()
        saved_theme = self._app_settings.get("theme", "dark")
        saved_lang = self._app_settings.get("language", "zh")
        init_theme()
        apply_theme(saved_theme)

        load_language(saved_lang)
        self.title("RSTao Remote Sensing Studio")
        self.geometry(Config.UI_CONSTANTS["default_window_size"])
        self.minsize(*Config.UI_CONSTANTS["min_window_size"])
        self.state("zoomed")

        self.project_manager = ProjectManager()
        self._auto_save_job = None
        self._init_window_icon()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_vars: Dict[str, ctk.StringVar] = {
            "coords": ctk.StringVar(value=""),
            "image_size": ctk.StringVar(value="无图像"),
            "algorithm": ctk.StringVar(value="就绪"),
            "features": ctk.StringVar(value="0"),
            "zoom": ctk.StringVar(value="100%"),
            "message": ctk.StringVar(value=""),
            "project_state": ctk.StringVar(value="未打开项目"),
        }

        self.feature_tab: Optional[FeatureTab] = None
        self.image_processing_tab: Optional[ImageProcessingTab] = None
        self.match_tab: Optional[MatchTab] = None
        self.vector_tab: Optional[VectorTab] = None

        self.project_name_label: Optional[ctk.CTkLabel] = None

        self.main_container = ctk.CTkFrame(self, fg_color=THEME["bg"])
        self.main_container.pack(fill="both", expand=True)

        # Keyboard shortcuts
        self.bind("<Control-s>", lambda e: self.save_project())
        self.bind("<Control-S>", lambda e: self.save_project())
        self.bind("<Control-n>", lambda e: self.new_project())
        self.bind("<Control-N>", lambda e: self.new_project())
        self.bind("<Control-o>", lambda e: self.open_project())
        # Drag & drop support (requires tkinterdnd2)
        try:
            self.drop_target_register("*")
            self.dnd_bind("<<Drop>>", self._on_drop)
        except AttributeError:
            pass  # tkinterdnd2 not available, drag-drop disabled
        self.show_welcome()

    def _init_window_icon(self):
        try:
            import sys
            from pathlib import Path

            from PIL import Image, ImageTk

            base_path = (
                Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent.parent
            )
            icon_path = base_path / "assets" / "icons" / "app.png"
            if icon_path.exists():
                img = Image.open(icon_path)
                tk_img = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, tk_img)
                self._icon_ref = tk_img  # prevent GC
        except Exception as e:
            logger.warning(f"加载窗口图标失败：{str(e)}")

    def show_welcome(self):
        self._clear_main_container()
        self.welcome_page = WelcomePage(
            self.main_container,
            self.new_project,
            self.open_project,
            self.open_recent_project,
            self.remove_recent_project,
            self.open_recent_location,
            self.prune_missing_recent_projects,
            self.clear_recent_projects,
        )
        self.welcome_page.update_recent_list(self.project_manager.recent_projects)
        self.welcome_page.pack(fill="both", expand=True)

    def show_main_interface(self):
        self._clear_main_container()
        try:
            self.create_menu_bar()
            self.workspace_frame = ctk.CTkFrame(self.main_container, fg_color=THEME["bg"])
            self.workspace_frame.pack(fill="both", expand=True)
            self.resource_panel = ResourcePanel(self.workspace_frame, self)
            self.resource_panel.pack(side="left", fill="y", padx=(8, 4), pady=8)
            self.content_frame = ctk.CTkFrame(self.workspace_frame, fg_color=THEME["bg"])
            self.content_frame.pack(side="right", fill="both", expand=True)
            self.create_statusbar()
            self.init_panels()
            self.refresh_resource_panel()
            if self.project_manager.current_project:
                project_name = self.project_manager.current_project.get("project_name", "未知项目")
                self.project_name_label.configure(text=project_name)
                self.restore_project_state()
                self._update_project_state()
            self._start_auto_save()
            logger.info("主工作界面初始化完成")
        except Exception as e:
            logger.error("初始化主界面失败", exc_info=True)
            show_actionable_error(
                self,
                "界面初始化失败",
                "主工作界面没有成功初始化。",
                "请查看日志；如果刚恢复项目，可尝试重新打开项目文件。",
                detail=str(e),
            )
            self.show_welcome()

    # ---- menu bar ----
    def create_menu_bar(self):
        """现代菜单栏"""
        self._menu_dropdown = None
        self._menu_buttons = []
        self._menubar_frame = ctk.CTkFrame(
            self.main_container, height=40, corner_radius=0, fg_color=THEME["menubar"]
        )
        self._menubar_frame.pack(fill="x")
        self._menubar_frame.pack_propagate(False)

        ctk.CTkLabel(
            self._menubar_frame,
            text="  RSTao-Tool",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=THEME["accent"],
        ).pack(side="left", padx=(8, 16))

        self._add_menu_button(
            "文件",
            [
                (f"{t('menu.new', '新建项目')}      Ctrl+N", self.new_project),
                (f"{t('menu.open', '打开项目')}      Ctrl+O", self.open_project),
                ("导入资源...", self.import_resources),
                ("---", None),
                (f"{t('menu.save', '保存')}      Ctrl+S", self.save_project),
                (f"{t('menu.export', '导出')}      Ctrl+E", self.export_current),
                (f"{t('menu.report', '导出报告')}      Ctrl+R", self.export_report),
                ("---", None),
                ("退出", self.quit),
            ],
        )
        self._add_menu_button(
            "功能",
            [
                (t("tab.feature", "特征检测"), lambda: self.switch_panel("feature")),
                ("图像处理", lambda: self.switch_panel("image_processing")),
                (t("tab.match", "影像匹配"), lambda: self.switch_panel("match")),
                (t("tab.vector", "矢量编辑"), lambda: self.switch_panel("vector")),
                (t("tab.coordinate", "坐标转换"), lambda: self.switch_panel("coordinate")),
                (t("tab.detection", "目标检测"), lambda: self.switch_panel("detection")),
                ("---", None),
                (t("menu.batch", "批量处理") + "...", self.open_batch_dialog),
            ],
        )
        self._add_menu_button(
            t("tab.settings", "设置"),
            [
                (t("settings.title", "偏好设置"), lambda: self.switch_panel("settings")),
            ],
        )
        self._add_menu_button(
            t("menu.help", "帮助"),
            [
                ("使用帮助  F1", self.show_help),
                ("结果历史...", self.open_result_history),
                ("运行日志...", self.open_log_viewer),
                ("插件管理...", self.open_plugin_dialog),
                (t("menu.about", "关于"), self.show_about),
            ],
        )

        self.bind_all("<Control-n>", lambda e: self.new_project())
        self.bind_all("<Control-o>", lambda e: self.open_project())
        self.bind_all("<Control-s>", lambda e: self.save_project())
        self.bind_all("<Control-e>", lambda e: self.export_current())
        self.bind_all("<Control-r>", lambda e: self.export_report())
        self.bind_all("<Button-1>", self._on_global_click, add="+")

    def _add_menu_button(self, text, items):
        btn = ctk.CTkButton(
            self._menubar_frame,
            text=text,
            width=64,
            height=38,
            fg_color="transparent",
            hover_color=THEME["hover"],
            text_color=THEME["text_primary"],
            font=("Microsoft YaHei UI", 12),
            corner_radius=6,
        )
        btn.configure(command=lambda i=items, b=btn: self._show_menu_dropdown(i, b))
        btn.pack(side="left", padx=1)
        self._menu_buttons.append(btn)

    def _show_menu_dropdown(self, items, parent_btn):
        self._hide_menu_dropdown()
        x = parent_btn.winfo_rootx() - self.winfo_rootx()
        y = parent_btn.winfo_rooty() - self.winfo_rooty() + parent_btn.winfo_height()
        dropdown = ctk.CTkFrame(
            self,
            fg_color=THEME["dropdown"],
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
        )
        for item_text, item_cmd in items:
            if item_text == "---":
                ctk.CTkFrame(dropdown, height=1, fg_color=THEME["border"]).pack(
                    fill="x", padx=8, pady=3
                )
            else:
                label = item_text.split("  ")[0].strip()
                row_btn = ctk.CTkButton(
                    dropdown,
                    text="  " + label,
                    anchor="w",
                    fg_color="transparent",
                    hover_color=THEME["hover"],
                    text_color=THEME["text_primary"],
                    font=FONT_NORMAL,
                    corner_radius=0,
                    height=30,
                    command=lambda c=item_cmd: (self._hide_menu_dropdown(), c() if c else None),
                )
                row_btn.pack(fill="x")
        dropdown.place(x=x, y=y)
        dropdown.lift()
        self._menu_dropdown = dropdown
        self._menu_dropdown_btn = parent_btn

    def _on_global_click(self, event):
        if self._menu_dropdown and self._menu_dropdown.winfo_exists():
            widget = event.widget
            if not str(widget).startswith(str(self._menu_dropdown)):
                if not (
                    hasattr(self, "_menu_dropdown_btn")
                    and str(widget).startswith(str(self._menu_dropdown_btn))
                ):
                    self._hide_menu_dropdown()

    def _hide_menu_dropdown(self):
        if self._menu_dropdown and self._menu_dropdown.winfo_exists():
            self._menu_dropdown.destroy()
        self._menu_dropdown = None

    def refresh_theme(self):
        """刷新所有组件主题"""
        if hasattr(self, "main_container") and self.main_container.winfo_exists():
            self.main_container.configure(fg_color=THEME["bg"])
        if hasattr(self, "_menubar_frame") and self._menubar_frame.winfo_exists():
            self._menubar_frame.configure(fg_color=THEME["menubar"])
            for child in self._menubar_frame.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    try:
                        child.configure(text_color=THEME["accent"])
                    except Exception:
                        pass
        for btn in getattr(self, "_menu_buttons", []):
            if btn.winfo_exists():
                btn.configure(
                    fg_color="transparent",
                    hover_color=THEME["hover"],
                    text_color=THEME["text_primary"],
                )
        if hasattr(self, "content_frame") and self.content_frame.winfo_exists():
            self.content_frame.configure(fg_color=THEME["bg"])
        if hasattr(self, "statusbar") and self.statusbar.winfo_exists():
            self.statusbar.configure(fg_color=THEME["statusbar"])
        for panel in getattr(self, "panels", {}).values():
            if panel.winfo_exists():
                try:
                    panel.configure(fg_color=THEME["bg"])
                except Exception:
                    pass
        if hasattr(self, "settings_tab") and self.settings_tab and self.settings_tab.winfo_exists():
            try:
                self.settings_tab.configure(fg_color=THEME["bg"])
            except Exception:
                pass
        self.configure(fg_color=THEME["bg"])

    def init_panels(self):
        """初始化功能面板"""
        self.panels = {}
        self.current_panel = None
        self.panels["feature"] = FeatureTab(self.content_frame, self.status_vars)
        self.panels["image_processing"] = ImageProcessingTab(self.content_frame, self.status_vars)
        self.panels["match"] = MatchTab(self.content_frame, self.status_vars)
        self.panels["vector"] = VectorTab(self.content_frame, self.status_vars)
        self.panels["coordinate"] = CoordinateTab(self.content_frame, self.status_vars)
        self.panels["detection"] = DetectionTab(self.content_frame, self.status_vars)
        self.panels["settings"] = SettingsTab(self.content_frame)
        self.feature_tab = self.panels["feature"]
        self.image_processing_tab = self.panels["image_processing"]
        self.match_tab = self.panels["match"]
        self.vector_tab = self.panels["vector"]
        self.coordinate_tab = self.panels["coordinate"]
        self.detection_tab = self.panels["detection"]
        self.settings_tab = self.panels["settings"]

    def switch_panel(self, name):
        """切换显示的功能面板"""
        if self.current_panel:
            self.current_panel.pack_forget()
        panel = self.panels.get(name)
        if panel:
            panel.pack(fill="both", expand=True)
            self.current_panel = panel
            self._current_panel_name = name

    def _clear_main_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def _on_drop(self, event):
        """Handle file drop on window"""
        try:
            file_path = event.data.strip("{}")
            if any(
                file_path.lower().endswith(ext)
                for ext in [".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".img", ".jp2"]
            ):
                self._load_dropped_image(file_path)
            elif file_path.lower().endswith(".shp"):
                self._load_dropped_shapefile(file_path)
            elif any(
                file_path.lower().endswith(ext)
                for ext in [
                    ".pcd",
                    ".las",
                    ".laz",
                    ".xyz",
                    ".pts",
                    ".obj",
                    ".osgb",
                    ".ply",
                    ".onnx",
                    ".pt",
                    ".pth",
                    ".engine",
                ]
            ):
                self.add_resource_path(file_path)
            elif file_path.lower().endswith(".rstao"):
                self._load_project(file_path)
        except Exception:
            pass

    def _load_dropped_image(self, path):
        self.switch_panel("image_processing")
        if hasattr(self, "current_panel") and hasattr(self.current_panel, "load_image_silent"):
            self.current_panel.load_image_silent(path)

    def _load_dropped_shapefile(self, path):
        self.switch_panel("vector")
        if hasattr(self, "current_panel") and hasattr(self.current_panel, "load_shp_direct"):
            self.current_panel.load_shp_direct(path)

    def import_resources(self):
        if hasattr(self, "resource_panel"):
            self.resource_panel.import_resources()

    def add_resource_path(self, path: str, source_type: str = None):
        if not self.project_manager.current_project:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return None
        if hasattr(self, "resource_panel"):
            return self.resource_panel.add_path(path, source_type=source_type)
        return None

    def refresh_resource_panel(self):
        if hasattr(self, "resource_panel") and self.resource_panel.winfo_exists():
            self.resource_panel.refresh()

    def _on_delete_key(self):
        """处理 Delete 快捷键。"""
        if self.current_panel and hasattr(self.current_panel, "delete_selected"):
            self.current_panel.delete_selected()

    def _prompt_save_project(self) -> bool:
        if (
            self.project_manager.current_project
            and hasattr(self, "current_panel")
            and self.current_panel
            and self.project_manager.is_dirty
        ):
            if messagebox.askyesno("提示", "当前项目未保存，是否保存？"):
                return self.save_project()
        return True

    def create_statusbar(self):
        self.statusbar = ctk.CTkFrame(
            self.main_container, height=26, corner_radius=0, fg_color=THEME["statusbar"]
        )
        self.statusbar.pack(fill="x", side="bottom")
        self.project_name_label = ctk.CTkLabel(
            self.statusbar,
            text="未打开项目",
            font=("Microsoft YaHei UI", 10),
            text_color=THEME["text_secondary"],
        )
        self.project_name_label.pack(side="left", padx=12)
        self.status_message_label = ctk.CTkLabel(
            self.statusbar,
            textvariable=self.status_vars["message"],
            font=("Microsoft YaHei UI", 10),
            text_color=THEME["text_muted"],
        )
        self.status_message_label.pack(side="left", fill="x", expand=True, padx=10)
        for vn in ["zoom", "features", "algorithm", "image_size", "project_state"]:
            ctk.CTkLabel(
                self.statusbar,
                textvariable=self.status_vars[vn],
                font=("Microsoft YaHei UI", 10),
                text_color=THEME["text_muted"],
            ).pack(side="right", padx=10)

    def _add_status_separator(self):
        pass

    def show_status(self, message: str, level: str = "info", timeout: int = 3500):
        colors = {
            "info": THEME["text_secondary"],
            "success": THEME["success"],
            "warning": THEME["warning"],
            "error": THEME["danger"],
        }
        self.status_vars["message"].set(message)
        if hasattr(self, "status_message_label"):
            self.status_message_label.configure(
                text_color=colors.get(level, THEME["text_secondary"])
            )
        if timeout:
            self.after(timeout, lambda: self.status_vars["message"].set(""))

    def new_project(self):
        if not self._prompt_save_project():
            return

        dialog = ctk.CTkInputDialog(text="请输入项目名称：", title=t("menu.new", "新建项目"))
        project_name = (dialog.get_input() or "").strip()
        if not project_name:
            logger.info("用户取消输入项目名称")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".rstao",
            filetypes=[("RSTao项目文件", "*.rstao")],
            initialfile=f"{project_name}.rstao",
            title="保存新项目",
        )

        if not save_path:
            logger.info("用户取消选择保存路径")
            return

        try:
            if self.project_manager.new_project(project_name, save_path):
                self.show_main_interface()
                self._update_project_state()
                self.show_status("项目创建成功", "success")
            else:
                show_actionable_error(
                    self,
                    "项目创建失败",
                    "项目文件没有成功创建。",
                    "请检查保存目录是否可写，或换一个目录重试。",
                )
        except Exception as e:
            logger.error("创建新项目失败", exc_info=True)
            show_actionable_error(
                self,
                "创建项目失败",
                "新项目创建过程中出现异常。",
                "请检查项目名称和保存路径后重试。",
                detail=str(e),
            )

    def open_project(self):
        if not self._prompt_save_project():
            return

        path = filedialog.askopenfilename(
            filetypes=[("RSTao项目文件", "*.rstao")], title="打开RSTao项目"
        )

        if path:
            self._load_project(path)

    def open_recent_project(self, path: str):
        if not self._prompt_save_project():
            return
        self._load_project(path)

    def remove_recent_project(self, path: str):
        self.project_manager.remove_recent_project(path)
        if hasattr(self, "welcome_page"):
            self.welcome_page.update_recent_list(self.project_manager.recent_projects)

    def prune_missing_recent_projects(self):
        self.project_manager.prune_missing_recent_projects()
        if hasattr(self, "welcome_page"):
            self.welcome_page.update_recent_list(self.project_manager.recent_projects)

    def clear_recent_projects(self):
        if messagebox.askyesno("确认", "清空最近项目列表？"):
            self.project_manager.clear_recent_projects()
            if hasattr(self, "welcome_page"):
                self.welcome_page.update_recent_list(self.project_manager.recent_projects)

    def open_recent_location(self, path: str):
        parent = Path(path).parent
        if _safe_path_exists(parent):
            try:
                os.startfile(str(parent))
            except OSError:
                self.remove_recent_project(path)

    def _load_project(self, path: str):
        try:
            if self.project_manager.check_backup(path):
                use_backup = messagebox.askyesno(
                    "恢复备份",
                    "检测到比项目文件更新的备份，是否先从备份恢复？",
                )
                if use_backup:
                    self.project_manager.recover_from_backup(path)
            project = self.project_manager.load_project(path)
            if project:
                project_name = project.get("project_name", "未知项目")
                self.show_main_interface()
                self._update_project_state()
                self.show_status(f"项目 {project_name} 加载成功", "success")
            else:
                show_actionable_error(
                    self,
                    "项目加载失败",
                    "项目文件没有成功加载，文件可能已损坏。",
                    "请尝试从自动保存备份恢复，或检查文件是否被其它程序占用。",
                )
                self.show_welcome()
        except Exception as e:
            logger.error(f"加载项目失败 {path}", exc_info=True)
            show_actionable_error(
                self,
                "加载项目失败",
                "打开项目时发生异常。",
                "请确认项目文件存在且格式正确。",
                detail=str(e),
            )
            self.show_welcome()

    def save_project(self, notify: bool = True, autosave: bool = False):
        if not self.project_manager.current_project:
            return self.save_project_as() if notify else False

        if not hasattr(self, "current_panel") or not self.current_panel:
            if notify:
                messagebox.showwarning("提示", "请先创建或打开一个项目")
            return

        try:
            feature_state = self.feature_tab.get_state() if self.feature_tab else {}
            image_processing_state = (
                self.image_processing_tab.get_state()
                if self.image_processing_tab and hasattr(self.image_processing_tab, "get_state")
                else {}
            )
            match_state = self.match_tab.get_state() if self.match_tab else {}
            vector_state = self.vector_tab.get_state() if self.vector_tab else {}
            coordinate_state = (
                self.coordinate_tab.get_state()
                if self.coordinate_tab and hasattr(self.coordinate_tab, "get_state")
                else {}
            )
            detection_state = (
                self.detection_tab.get_state()
                if self.detection_tab and hasattr(self.detection_tab, "get_state")
                else {}
            )
            settings_state = (
                self.settings_tab.get_state()
                if self.settings_tab and hasattr(self.settings_tab, "get_state")
                else {}
            )
            current_tab = {
                "feature": "特征检测",
                "image_processing": "图像处理",
                "match": "影像匹配",
                "vector": "矢量编辑",
                "coordinate": "坐标转换",
                "detection": "目标检测",
                "settings": "设置",
            }.get(getattr(self, "_current_panel_name", "feature"), "特征检测")

            if self.project_manager.save_project(
                feature_state=feature_state,
                image_processing_state=image_processing_state,
                match_state=match_state,
                vector_state=vector_state,
                current_tab=current_tab,
                coordinate_state=coordinate_state,
                detection_state=detection_state,
                settings_state=settings_state,
                autosave=autosave,
            ):
                logger.info(f"项目保存成功：{self.project_manager.project_path}")
                self._update_project_state()
                if notify and not autosave:
                    self.show_status("项目保存成功", "success")
                return True
            else:
                if notify:
                    show_actionable_error(
                        self,
                        "项目保存失败",
                        "项目文件没有成功写入磁盘。",
                        "请检查磁盘空间、文件权限，或换一个目录另存为。",
                    )
                return False
        except Exception as e:
            logger.error("保存项目失败", exc_info=True)
            if notify:
                show_actionable_error(
                    self,
                    "保存项目失败",
                    "保存项目时发生异常。",
                    "请检查路径权限；当前窗口不会强制退出。",
                    detail=str(e),
                )
            return False

    def save_project_as(self):
        dialog = ctk.CTkInputDialog(text="请输入项目名称：", title="另存为")
        project_name = (dialog.get_input() or "").strip()
        if not project_name:
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".rstao",
            filetypes=[("RSTao项目文件", "*.rstao")],
            initialfile=f"{project_name}.rstao",
            title="项目另存为",
        )

        if not save_path:
            return

        try:
            if not self.project_manager.current_project:
                self.project_manager.new_project(project_name, save_path)
                self.show_main_interface()
            else:
                self.project_manager.current_project["project_name"] = project_name
                self.project_manager.project_path = save_path
                self.save_project()

            if self.project_name_label:
                self.project_name_label.configure(text=f"项目: {project_name}")
            self._update_project_state()
        except Exception as e:
            logger.error("项目另存为失败", exc_info=True)
            show_actionable_error(
                self,
                "另存为失败",
                "项目没有保存到新位置。",
                "请检查目标目录是否可写。",
                detail=str(e),
            )

    def restore_project_state(self):
        project = self.project_manager.current_project
        if not project:
            return

        try:
            current_tab = project.get("current_tab")
            if current_tab:
                tab_map = {
                    "特征检测": "feature",
                    "图像处理": "image_processing",
                    "影像匹配": "match",
                    "矢量编辑": "vector",
                    "坐标转换": "coordinate",
                    "目标检测": "detection",
                    "设置": "settings",
                }
                self.switch_panel(
                    current_tab
                    if current_tab in self.panels
                    else tab_map.get(current_tab, "feature")
                )

            if self.feature_tab and project.get("feature_tab"):
                self.feature_tab.set_state(project["feature_tab"])
            if (
                self.image_processing_tab
                and project.get("image_processing_tab")
                and hasattr(self.image_processing_tab, "set_state")
            ):
                self.image_processing_tab.set_state(project["image_processing_tab"])
            if self.match_tab and project.get("match_tab"):
                self.match_tab.set_state(project["match_tab"])
            if self.vector_tab and project.get("vector_tab"):
                self.vector_tab.set_state(project["vector_tab"])
            if (
                self.coordinate_tab
                and project.get("coordinate_tab")
                and hasattr(self.coordinate_tab, "set_state")
            ):
                self.coordinate_tab.set_state(project["coordinate_tab"])
            if (
                self.detection_tab
                and project.get("detection_tab")
                and hasattr(self.detection_tab, "set_state")
            ):
                self.detection_tab.set_state(project["detection_tab"])
            if (
                self.settings_tab
                and project.get("settings_tab")
                and hasattr(self.settings_tab, "set_state")
            ):
                self.settings_tab.set_state(project["settings_tab"])
        except Exception as e:
            logger.warning("恢复项目状态失败", exc_info=True)

    def on_close(self):
        # 保存窗口位置
        try:
            import re

            geo = self.geometry()
            m = re.match(r"(\d+)x(\d+)\+(\-?\d+)\+(\-?\d+)", geo)
            if m:
                self._app_settings["window"] = {
                    "width": int(m.group(1)),
                    "height": int(m.group(2)),
                    "x": int(m.group(3)),
                    "y": int(m.group(4)),
                }
                save_settings(self._app_settings)
        except Exception:
            pass
        try:
            self._stop_auto_save()
            if not self._prompt_save_project():
                return

            import matplotlib.pyplot as plt

            plt.close("all")

            self.quit()
            logger.info("程序正常退出")
        except Exception as e:
            logger.error("关闭窗口时出错", exc_info=True)
            sys.exit(1)

    def _start_auto_save(self):
        self._stop_auto_save()
        if self.project_manager.current_project:
            self._auto_save_job = self.after(180000, self._auto_save_tick)

    def _stop_auto_save(self):
        if self._auto_save_job:
            try:
                self.after_cancel(self._auto_save_job)
            except Exception:
                pass
            self._auto_save_job = None

    def _auto_save_tick(self):
        self._auto_save_job = None
        if self.project_manager.current_project:
            self.save_project(notify=False, autosave=True)
            if self.project_manager.current_project:
                self.status_vars["project_state"].set(
                    f"自动保存 {datetime.now().strftime('%H:%M:%S')}"
                )
            self._start_auto_save()

    def _check_backup_recovery(self):
        """Check for unsaved backup on startup"""
        import pathlib

        # Search for autosaves in the project directory.
        search_dir = (
            pathlib.Path(self.project_manager.project_path).parent
            if self.project_manager.project_path
            else pathlib.Path.cwd()
        )
        backup_files = list(search_dir.glob("*.rstao.autosave"))
        if not backup_files:
            return
        from tkinter import messagebox as mb

        for bak in backup_files[:5]:  # Check recent backups
            proj_path = str(bak.with_suffix(""))
            if bak.exists() and not pathlib.Path(proj_path).exists():
                result = mb.askyesno(
                    "崩溃恢复", f"检测到未保存的项目备份：\n{bak.name}\n\n是否恢复？"
                )
                if result and self.project_manager.recover_from_backup(proj_path):
                    mb.showinfo("恢复成功", f"项目已从备份恢复：\n{proj_path}")
                    self._load_project(proj_path)
                    break

    def export_current(self):
        if not hasattr(self, "current_panel") or not self.current_panel:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return

        cur_tab = getattr(self, "_current_panel_name", "feature")
        try:
            if cur_tab in ("特征检测", "feature") and self.feature_tab:
                self.feature_tab.save_result()
            elif cur_tab in ("图像处理", "image_processing") and self.image_processing_tab:
                self.image_processing_tab.save_result()
            elif cur_tab in ("影像匹配", "match") and self.match_tab:
                self.match_tab.save_result()
            elif cur_tab in ("矢量编辑", "vector") and self.vector_tab:
                self.vector_tab.export_file()
            # 各标签页内部自行提示（取消时不弹窗）
        except Exception as e:
            logger.error(f"导出 {cur_tab} 失败", exc_info=True)
            messagebox.showerror("导出失败", f"导出失败：{str(e)}")

    def show_help(self):
        help_text = t("help.content", "RSTao Remote Sensing Studio")
        messagebox.showinfo(t("help.title", "软件帮助"), help_text.strip())

    def open_plugin_dialog(self):
        """打开插件管理对话框"""
        PluginDialog(self)

    def open_result_history(self):
        if not self.project_manager.current_project:
            messagebox.showwarning("提示", "请先创建或打开一个项目。")
            return
        ResultHistoryDialog(self)

    def open_log_viewer(self):
        LogViewerDialog(self)

    def export_report(self):
        """导出匹配精度报告"""
        from tkinter import filedialog as fd

        from core.report_generator import FeatureStats, MatchStats, ReportGenerator
        from core.spatial_reference import format_spatial_ref

        path = fd.asksaveasfilename(
            defaultextension=".html", filetypes=[("HTML 报告", "*.html")], title="导出精度报告"
        )
        if not path:
            return
        info = {}
        if self.project_manager.current_project:
            project = self.project_manager.current_project
            info["项目名称"] = project.get("project_name", "")
            data_sources = project.get("data_sources", [])
            result_history = project.get("result_history", [])
            if data_sources:
                info["数据源数量"] = str(len(data_sources))
                info["空间参考"] = "\n".join(
                    format_spatial_ref(source) for source in data_sources[:8]
                )
            if result_history:
                info["结果记录"] = str(len(result_history))
        if (
            hasattr(self, "match_tab")
            and self.match_tab
            and hasattr(self.match_tab, "correlation_map")
            and self.match_tab.correlation_map is not None
        ):
            stats = MatchStats()
            cmap = self.match_tab.correlation_map
            stats.scores = cmap.flatten().tolist()[:5000]
            stats.total_pairs = len(stats.scores)
            stats.successful_pairs = stats.total_pairs
            stats.compute()
            rg = ReportGenerator()
            rg.generate_match_report("RSTao-Tool 匹配精度报告", stats, info, path)
        else:
            stats = FeatureStats()
            stats.compute()
            rg = ReportGenerator()
            rg.generate_feature_report("RSTao-Tool 分析报告", stats, info, path)
        if self.project_manager.current_project:
            self.project_manager.add_result_record(
                "report",
                "导出分析报告",
                outputs=[path],
                metrics={"score_count": getattr(stats, "total_pairs", 0)},
            )
        self.show_status(f"报告已导出：{path}", "success")

    def open_batch_dialog(self):
        BatchDialog(self)

    def _mark_project_dirty(self):
        if self.project_manager.current_project:
            self.project_manager.mark_dirty()
            self._update_project_state()

    def _update_project_state(self):
        project = self.project_manager.current_project
        if not project:
            self.title("RSTao Remote Sensing Studio")
            self.status_vars["project_state"].set("未打开项目")
            return
        name = project.get("project_name", "未知项目")
        dirty_prefix = "* " if self.project_manager.is_dirty else ""
        self.title(f"{dirty_prefix}{name} - RSTao Remote Sensing Studio")
        if self.project_name_label:
            self.project_name_label.configure(text=f"{dirty_prefix}{name}")
        if self.project_manager.is_dirty:
            self.status_vars["project_state"].set("有未保存修改")
        elif self.project_manager.last_saved_at:
            self.status_vars["project_state"].set(f"已保存 {self.project_manager.last_saved_at}")
        else:
            self.status_vars["project_state"].set("已保存")

    def show_about(self):
        lic = LicenseManager.get_license_info()
        about_text = f"""
RSTao Remote Sensing Studio
===========================
基于 Python+OpenCV+CustomTkinter 开发

作者：{APP_AUTHOR}
版本：{APP_VERSION}
发布日期：{RELEASE_DATE}

—————————— 真实软件授权信息 ——————————
授权状态：{lic['status']}
授权类型：{lic['type']}
过期时间：{lic['expire']}
剩余可用：{lic['remain']}
绑定机器码：{lic.get('machine', '无')}

©2026 RSTao-Tool 保留全部著作权
        """
        messagebox.showinfo(t("menu.about", "关于软件"), about_text.strip())


if __name__ == "__main__":
    try:
        app = MainWindow()
        app.mainloop()
    except Exception as e:
        logger.critical("程序启动失败", exc_info=True)
        messagebox.showerror("致命错误", f"程序启动失败：{str(e)}")
        sys.exit(1)
