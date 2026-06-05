import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
import tkinter as tk
from PIL import Image

from common.crypto import aes_gcm_decrypt
from common.logger import logger
from core.project_manager import ProjectManager

# 本地模块导入
from .feature_tab import FeatureTab
from .match_tab import MatchTab
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
from .settings_tab import SettingsTab
from .batch_dialog import BatchDialog
from .coordinate_tab import CoordinateTab
from .detection_tab import DetectionTab
from .plugin_dialog import PluginDialog


# ====================== 配置常量（集中管理） ======================
class Config:
    LICENSE_FILE = Path(__file__).parent.parent / ".license.dat"
    ICONS_DIR = Path(__file__).parent.parent / "assets/icons"
    RECENT_PROJECTS_MAX = 10
    UI_CONSTANTS = {
        "welcome_padx": 300,
        "ribbon_height": 60,
        "statusbar_height": 25,
        "btn_icon_size": (20, 20),
        "app_icon_size": (32, 32),
        "default_window_size": "1600x900",
        "min_window_size": (1400, 800),
    }


# ====================== 授权管理类 ======================
class LicenseManager:
    @staticmethod
    def decrypt_license(encrypted_key: str) -> tuple[Optional[str], Optional[float]]:
        try:
            decrypted_str = aes_gcm_decrypt(encrypted_key)
            if decrypted_str is None:
                logger.error("授权解密失败：密钥无效或被篡改")
                return None, None

            # 全部分割竖线，永远只取前两项
            parts = decrypted_str.split("|")
            if len(parts) >= 2:
                machine_code = parts[0].strip()
                expire_ts = parts[1].strip()
                return machine_code, float(expire_ts)
            logger.error(f"解密内容字段不足：{decrypted_str}")
            return None, None

        except Exception as e:
            logger.error(f"授权解密失败：{str(e)}", exc_info=True)
            return None, None

    @staticmethod
    def get_license_info() -> Dict[str, str]:
        # 初始化默认值，避免变量未定义报错
        default_info = {
            "status": "未授权",
            "type": "无授权",
            "expire": "无",
            "remain": "无",
            "machine": "无",
        }
        license_type = "无授权"
        status = "未授权"
        expire_str = "无"
        remain_days = "无"
        machine = "无"

        if not Config.LICENSE_FILE.exists():
            logger.info("授权文件 .license.dat 不存在")
            return default_info

        try:
            with open(Config.LICENSE_FILE, "r", encoding="utf-8") as f:
                encrypted_key = f.read().strip()

            if not encrypted_key:
                return {
                    "status": "授权文件为空",
                    "type": "无",
                    "expire": "无",
                    "remain": "无",
                    "machine": "无",
                }

            machine, expire_ts = LicenseManager.decrypt_license(encrypted_key)
            if not machine or expire_ts is None:
                return {
                    "status": "授权无效",
                    "type": "无效授权",
                    "expire": "无",
                    "remain": "无",
                    "machine": "无",
                }

            expire_date = datetime.fromtimestamp(expire_ts)
            now = datetime.now()
            permanent_date = datetime(2099, 12, 31)

            if abs((expire_date - permanent_date).days) < 10:
                license_type = "永久授权"
                remain_days = "永久有效"
                status = "已授权（永久）"
                expire_str = "2099-12-31 永久"
            else:
                remain_days_int = (expire_date - now).days
                expire_str = expire_date.strftime("%Y-%m-%d %H:%M:%S")
                license_type = "限时试用授权"
                if remain_days_int < 0:
                    status = f"已过期 {abs(remain_days_int)} 天"
                    remain_days = f"已过期{abs(remain_days_int)}天"
                else:
                    status = "正常使用"
                    remain_days = f"{remain_days_int} 天"

            return {
                "status": status,
                "type": license_type,
                "machine": machine,
                "expire": expire_str,
                "remain": remain_days,
            }
        except Exception as e:
            logger.error(f"解析授权文件失败：{str(e)}")
            return {
                "status": "授权文件损坏",
                "type": license_type,
                "expire": expire_str,
                "remain": remain_days,
                "machine": machine,
            }


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


class WelcomePage(ctk.CTkFrame):
    """欢迎页 - Hero 布局"""
    def __init__(self, parent, new_project_callback, open_project_callback, open_recent_callback):
        super().__init__(parent, fg_color=THEME["bg"])
        self.new_project_callback = new_project_callback
        self.open_project_callback = open_project_callback
        self.open_recent_callback = open_recent_callback

        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.pack(pady=(80, 30))
        ctk.CTkLabel(hero, text="RSTao-Tool", font=("Microsoft YaHei UI", 42, "bold"),
                    text_color=THEME["accent"]).pack()
        ctk.CTkLabel(hero, text="Remote Sensing Tool", font=("Microsoft YaHei UI", 14),
                    text_color=THEME["text_secondary"]).pack(pady=(4, 20))
        sep = ctk.CTkFrame(hero, height=1, width=120, fg_color=THEME["border"])
        sep.pack()
        ctk.CTkLabel(hero, text="专业遥感影像处理与分析平台", font=("Microsoft YaHei UI", 13),
                    text_color=THEME["text_muted"]).pack(pady=(16, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=20)
        bs = {"width": 200, "height": 42, "font": FONT_NORMAL, "corner_radius": 8}
        ctk.CTkButton(actions, text="+  新建项目", fg_color=THEME["accent"],
                     hover_color=THEME["accent_hover"], command=self.new_project_callback, **bs).pack(pady=4)
        ctk.CTkButton(actions, text="打开已有项目", fg_color="transparent", border_width=1,
                     border_color=THEME["border"], text_color=THEME["text_primary"],
                     hover_color=THEME["hover"], command=self.open_project_callback, **bs).pack(pady=4)

        ctk.CTkLabel(self, text="最近打开", font=("Microsoft YaHei UI", 11, "bold"),
                    text_color=THEME["text_muted"]).pack(pady=(50, 8))
        self.recent_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=10,
                                         border_width=1, border_color=THEME["border"])
        self.recent_frame.pack(fill="x", padx=360)
        self.update_recent_list([])

    def update_recent_list(self, recent_projects):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        display = recent_projects[:Config.RECENT_PROJECTS_MAX]
        if not display:
            ctk.CTkLabel(self.recent_frame, text="暂无最近项目", font=FONT_SMALL,
                        text_color=THEME["text_muted"]).pack(pady=16)
            return
        for path in display:
            p = Path(path)
            if p.exists():
                name = p.stem[:36] + "..." if len(p.stem) > 36 else p.stem
                row = ctk.CTkFrame(self.recent_frame, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)
                ctk.CTkLabel(row, text=name, font=FONT_SMALL,
                            text_color=THEME["text_secondary"]).pack(side="left", padx=6)
                ctk.CTkButton(row, text="打开", width=50, height=24, font=("Microsoft YaHei UI", 10),
                             fg_color="transparent", hover_color=THEME["hover"],
                             text_color=THEME["accent"],
                             command=lambda pp=path: self.open_recent_callback(pp)).pack(side="right", padx=6)


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        init_theme()

        self.title("RSTao Remote Sensing Studio")
        self.geometry(Config.UI_CONSTANTS["default_window_size"])
        self.minsize(*Config.UI_CONSTANTS["min_window_size"])
        self.state("zoomed")

        self.project_manager = ProjectManager()
        self._init_window_icon()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_vars: Dict[str, ctk.StringVar] = {
            "coords": ctk.StringVar(value=""),
            "image_size": ctk.StringVar(value="无图像"),
            "algorithm": ctk.StringVar(value="就绪"),
            "features": ctk.StringVar(value="0"),
            "zoom": ctk.StringVar(value="100%"),
        }

        self.feature_tab: Optional[FeatureTab] = None
        self.match_tab: Optional[MatchTab] = None
        self.vector_tab: Optional[VectorTab] = None

        self.project_name_label: Optional[ctk.CTkLabel] = None

        self.main_container = ctk.CTkFrame(self, fg_color=THEME["bg"])
        self.main_container.pack(fill="both", expand=True)

        self.show_welcome()

    def _init_window_icon(self):
        try:
            app_icon = load_icon("app", Config.UI_CONSTANTS["app_icon_size"])
            if app_icon:
                self.wm_iconphoto(True, app_icon)
        except Exception as e:
            logger.warning(f"加载窗口图标失败：{str(e)}")

    def show_welcome(self):
        self._clear_main_container()
        self.welcome_page = WelcomePage(
            self.main_container, self.new_project, self.open_project, self.open_recent_project
        )
        self.welcome_page.update_recent_list(self.project_manager.recent_projects)
        self.welcome_page.pack(fill="both", expand=True)

    def show_main_interface(self):
        self._clear_main_container()
        try:
            self.create_menu_bar()
            self.content_frame = ctk.CTkFrame(self.main_container, fg_color=THEME["bg"])
            self.content_frame.pack(fill="both", expand=True)
            self.create_statusbar()
            self.init_panels()
            if self.project_manager.current_project:
                project_name = self.project_manager.current_project.get("project_name", "未知项目")
                self.project_name_label.configure(text=project_name)
                self.restore_project_state()
            logger.info("主工作界面初始化完成")
        except Exception as e:
            logger.error("初始化主界面失败", exc_info=True)
            messagebox.showerror("错误", f"界面初始化失败：{str(e)}")
            self.show_welcome()

    # ---- menu bar ----
    def create_menu_bar(self):
        """现代菜单栏"""
        self._menu_dropdown = None
        self._menu_buttons = []
        self._menubar_frame = ctk.CTkFrame(self.main_container, height=40, corner_radius=0, fg_color=THEME["menubar"])
        self._menubar_frame.pack(fill="x")
        self._menubar_frame.pack_propagate(False)

        ctk.CTkLabel(self._menubar_frame, text="  RSTao-Tool", font=("Microsoft YaHei UI", 12, "bold"),
                    text_color=THEME["accent"]).pack(side="left", padx=(8, 16))

        self._add_menu_button("文件", [
            ("新建项目      Ctrl+N", self.new_project),
            ("打开项目      Ctrl+O", self.open_project),
            ("---", None),
            ("保存项目      Ctrl+S", self.save_project),
            ("导出结果      Ctrl+E", self.export_current),
            ("导出报告      Ctrl+R", self.export_report),
            ("---", None),
            ("退出", self.quit),
        ])
        self._add_menu_button("功能", [
            ("特征检测", lambda: self.switch_panel("feature")),
            ("影像匹配", lambda: self.switch_panel("match")),
            ("矢量编辑", lambda: self.switch_panel("vector")),
            ("坐标转换", lambda: self.switch_panel("coordinate")),
            ("目标检测", lambda: self.switch_panel("detection")),
            ("---", None),
            ("批量处理...", self.open_batch_dialog),
        ])
        self._add_menu_button("设置", [
            ("偏好设置", lambda: self.switch_panel("settings")),
        ])
        self._add_menu_button("帮助", [
            ("使用帮助  F1", self.show_help),
            ("插件管理...", self.open_plugin_dialog),
            ("关于", self.show_about),
        ])

        self.bind_all("<Control-n>", lambda e: self.new_project())
        self.bind_all("<Control-o>", lambda e: self.open_project())
        self.bind_all("<Control-s>", lambda e: self.save_project())
        self.bind_all("<Control-e>", lambda e: self.export_current())
        self.bind_all("<Control-r>", lambda e: self.export_report())
        self.bind_all("<Button-1>", self._on_global_click, add="+")

    def _add_menu_button(self, text, items):
        btn = ctk.CTkButton(
            self._menubar_frame, text=text, width=64, height=38,
            fg_color="transparent", hover_color=THEME["hover"],
            text_color=THEME["text_primary"],
            font=("Microsoft YaHei UI", 12), corner_radius=6,
        )
        btn.configure(command=lambda i=items, b=btn: self._show_menu_dropdown(i, b))
        btn.pack(side="left", padx=1)
        self._menu_buttons.append(btn)

    def _show_menu_dropdown(self, items, parent_btn):
        self._hide_menu_dropdown()
        x = parent_btn.winfo_rootx() - self.winfo_rootx()
        y = parent_btn.winfo_rooty() - self.winfo_rooty() + parent_btn.winfo_height()
        dropdown = ctk.CTkFrame(
            self, fg_color=THEME["dropdown"],
            corner_radius=6, border_width=1, border_color=THEME["border"]
        )
        for item_text, item_cmd in items:
            if item_text == "---":
                ctk.CTkFrame(dropdown, height=1, fg_color=THEME["border"]).pack(fill="x", padx=8, pady=3)
            else:
                label = item_text.split("  ")[0].strip()
                row_btn = ctk.CTkButton(
                    dropdown, text="  " + label, anchor="w",
                    fg_color="transparent", hover_color=THEME["hover"],
                    text_color=THEME["text_primary"],
                    font=FONT_NORMAL, corner_radius=0, height=30,
                    command=lambda c=item_cmd: (self._hide_menu_dropdown(), c() if c else None)
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
                if not (hasattr(self, "_menu_dropdown_btn") and str(widget).startswith(str(self._menu_dropdown_btn))):
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
                btn.configure(fg_color="transparent", hover_color=THEME["hover"], text_color=THEME["text_primary"])
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
        self.panels["match"] = MatchTab(self.content_frame, self.status_vars)
        self.panels["vector"] = VectorTab(self.content_frame, self.status_vars)
        self.panels["coordinate"] = CoordinateTab(self.content_frame, self.status_vars)
        self.panels["detection"] = DetectionTab(self.content_frame, self.status_vars)
        self.panels["settings"] = SettingsTab(self.content_frame)
        self.feature_tab = self.panels["feature"]
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


    def _clear_main_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def _prompt_save_project(self) -> bool:
        if self.project_manager.current_project and hasattr(self, 'current_panel') and self.current_panel:
            if messagebox.askyesno("提示", "当前项目未保存，是否保存？"):
                return self.save_project()
        return True


    def create_statusbar(self):
        self.statusbar = ctk.CTkFrame(self.main_container, height=26, corner_radius=0, fg_color=THEME["statusbar"])
        self.statusbar.pack(fill="x", side="bottom")
        self.project_name_label = ctk.CTkLabel(self.statusbar, text="未打开项目",
                                              font=("Microsoft YaHei UI", 10), text_color=THEME["text_secondary"])
        self.project_name_label.pack(side="left", padx=12)
        for vn in ["zoom", "features", "algorithm", "image_size"]:
            ctk.CTkLabel(self.statusbar, textvariable=self.status_vars[vn],
                        font=("Microsoft YaHei UI", 10), text_color=THEME["text_muted"]).pack(side="right", padx=10)

    def _add_status_separator(self):
        pass

    def _add_status_separator(self):
        pass


    def new_project(self):
        if not self._prompt_save_project():
            return

        dialog = ctk.CTkInputDialog(text="请输入项目名称：", title="新建项目")
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
                messagebox.showinfo("成功", "项目创建成功")
                self.show_main_interface()
            else:
                messagebox.showerror("错误", "项目创建失败")
        except Exception as e:
            logger.error("创建新项目失败", exc_info=True)
            messagebox.showerror("错误", f"创建项目失败：{str(e)}")

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

    def _load_project(self, path: str):
        try:
            project = self.project_manager.load_project(path)
            if project:
                project_name = project.get("project_name", "未知项目")
                messagebox.showinfo("成功", f"项目 {project_name} 加载成功")
                self.show_main_interface()
            else:
                messagebox.showerror("错误", "项目加载失败，文件可能已损坏")
                self.show_welcome()
        except Exception as e:
            logger.error(f"加载项目失败 {path}", exc_info=True)
            messagebox.showerror("错误", f"加载项目失败：{str(e)}")
            self.show_welcome()

    def save_project(self):
        if not self.project_manager.current_project:
            return self.save_project_as()

        if not hasattr(self, "current_panel") or not self.current_panel:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return

        try:
            feature_state = self.feature_tab.get_state() if self.feature_tab else {}
            match_state = self.match_tab.get_state() if self.match_tab else {}
            vector_state = self.vector_tab.get_state() if self.vector_tab else {}
            current_tab = "特征检测"  # default

            if self.project_manager.save_project(
                feature_state, match_state, vector_state, current_tab
            ):
                logger.info(f"项目保存成功：{self.project_manager.project_path}")
                messagebox.showinfo("成功", "项目保存成功")
                return True
            else:
                messagebox.showerror("错误", "项目保存失败")
                return False
        except Exception as e:
            logger.error("保存项目失败", exc_info=True)
            messagebox.showerror("错误", f"保存项目失败：{str(e)}")
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
            self.project_manager.current_project["project_name"] = project_name
            self.project_manager.project_path = save_path
            self.save_project()

            if self.project_name_label:
                self.project_name_label.configure(text=f"项目: {project_name}")
        except Exception as e:
            logger.error("项目另存为失败", exc_info=True)
            messagebox.showerror("错误", f"另存为失败：{str(e)}")

    def restore_project_state(self):
        project = self.project_manager.current_project
        if not project:
            return

        try:
            current_tab = project.get("current_tab")
            if current_tab:
                tab_map = {"特征检测":"feature","影像匹配":"match","矢量编辑":"vector"}
                self.switch_panel(tab_map.get(current_tab, "feature"))

            if self.feature_tab and project.get("feature_tab"):
                self.feature_tab.set_state(project["feature_tab"])
            if self.match_tab and project.get("match_tab"):
                self.match_tab.set_state(project["match_tab"])
            if self.vector_tab and project.get("vector_tab"):
                self.vector_tab.set_state(project["vector_tab"])
        except Exception as e:
            logger.warning("恢复项目状态失败", exc_info=True)

    def on_close(self):
        try:
            self._prompt_save_project()

            import matplotlib.pyplot as plt

            plt.close("all")

            self.quit()
            logger.info("程序正常退出")
        except Exception as e:
            logger.error("关闭窗口时出错", exc_info=True)
            sys.exit(1)

    def export_current(self):
        if not hasattr(self, "current_panel") or not self.current_panel:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return

        cur_tab = getattr(self, "_current_panel_name", "feature")
        try:
            if cur_tab == "特征检测" and self.feature_tab:
                self.feature_tab.save_result()
            elif cur_tab == "影像匹配" and self.match_tab:
                self.match_tab.save_result()
            elif cur_tab == "矢量编辑" and self.vector_tab:
                self.vector_tab.export_file()
            # 各标签页内部自行提示（取消时不弹窗）
        except Exception as e:
            logger.error(f"导出 {cur_tab} 失败", exc_info=True)
            messagebox.showerror("导出失败", f"导出失败：{str(e)}")

    def show_help(self):
        help_text = """
RSTao Remote Sensing Studio
============================
专业遥感RSTao-Tool与分析工具

【功能模块】
1. 特征检测：Harris、Moravec、Forstner、SUSAN角点检测
2. 影像匹配：单目标匹配、多目标匹配、模板匹配
3. 矢量编辑：SHP文件加载、要素绘制、属性编辑

【快捷键】
- 鼠标滚轮：缩放视图
- 右键：取消当前操作
- 双击：结束绘制

© 2026 RSTao Studio 版权所有
        """
        messagebox.showinfo("软件帮助", help_text.strip())

    def open_plugin_dialog(self):
        """打开插件管理对话框"""
        PluginDialog(self)

    def export_report(self):
        """导出匹配精度报告"""
        from tkinter import filedialog as fd
        from core.report_generator import ReportGenerator, MatchStats, FeatureStats
        path = fd.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML 报告", "*.html")],
            title="导出精度报告"
        )
        if not path:
            return
        info = {}
        if self.project_manager.current_project:
            info["项目名称"] = self.project_manager.current_project.get("project_name", "")
        if hasattr(self, "match_tab") and self.match_tab and hasattr(self.match_tab, "correlation_map") and self.match_tab.correlation_map is not None:
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
        messagebox.showinfo("成功", f"报告已导出至:\n{path}")

    def open_batch_dialog(self):
        BatchDialog(self)

    def open_plugin_dialog(self):
        PluginDialog(self)

    def export_report(self):
        from tkinter import filedialog as fd
        from core.report_generator import ReportGenerator, MatchStats, FeatureStats
        path = fd.asksaveasfilename(defaultextension=".html", filetypes=[("HTML 报告", "*.html")], title="导出精度报告")
        if not path:
            return
        info = {}
        if self.project_manager.current_project:
            info["项目名称"] = self.project_manager.current_project.get("project_name", "")
        if hasattr(self, "match_tab") and self.match_tab and hasattr(self.match_tab, "correlation_map") and self.match_tab.correlation_map is not None:
            stats = MatchStats()
            stats.scores = self.match_tab.correlation_map.flatten().tolist()[:5000]
            stats.total_pairs = len(stats.scores)
            stats.successful_pairs = stats.total_pairs
            stats.compute()
            ReportGenerator().generate_match_report("RSTao-Tool 匹配精度报告", stats, info, path)
        else:
            stats = FeatureStats()
            stats.compute()
            ReportGenerator().generate_feature_report("RSTao-Tool 分析报告", stats, info, path)
        messagebox.showinfo("成功", f"报告已导出至:\n{path}")

    def show_about(self):
        lic = LicenseManager.get_license_info()
        about_text = f"""
RSTao Remote Sensing Studio
===========================
基于 Python+OpenCV+CustomTkinter 开发

作者：RSTao
版本：1.0.0
发布日期：2026-06-02

—————————— 真实软件授权信息 ——————————
授权状态：{lic['status']}
授权类型：{lic['type']}
过期时间：{lic['expire']}
剩余可用：{lic['remain']}
绑定机器码：{lic.get('machine', '无')}

©2026 RSTao-Tool 保留全部著作权
        """
        messagebox.showinfo("关于软件", about_text.strip())


if __name__ == "__main__":
    try:
        app = MainWindow()
        app.mainloop()
    except Exception as e:
        logger.critical("程序启动失败", exc_info=True)
        messagebox.showerror("致命错误", f"程序启动失败：{str(e)}")
        sys.exit(1)
