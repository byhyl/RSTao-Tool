import customtkinter as ctk
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Callable, Optional, List
from PIL import Image
from tkinter import filedialog, messagebox
import base64

# 本地模块导入
from .feature_tab import FeatureTab
from .match_tab import MatchTab
from .vector_tab import VectorTab
from .theme import init_theme, THEME, FONT_TITLE, FONT_SUBTITLE, FONT_NORMAL, FONT_SMALL, PANEL_STYLE
from core.project_manager import ProjectManager
from common.crypto import aes_gcm_decrypt
from common.logger import logger

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
        "min_window_size": (1400, 800)
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
        default_info = {"status": "未授权", "type": "无授权", "expire": "无", "remain": "无", "machine": "无"}
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
                return {"status": "授权文件为空", "type": "无", "expire": "无", "remain": "无", "machine": "无"}
        
            machine, expire_ts = LicenseManager.decrypt_license(encrypted_key)
            if not machine or expire_ts is None:
                return {"status": "授权无效", "type": "无效授权", "expire": "无", "remain": "无", "machine": "无"}
        
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
                "remain": remain_days
                }
        except Exception as e:
            logger.error(f"解析授权文件失败：{str(e)}")
            return {"status": "授权文件损坏", "type": license_type, "expire": expire_str, "remain": remain_days, "machine": machine}

# ====================== 工具函数 ======================
def load_icon(icon_name: str, size: tuple[int, int] = (24, 24)) -> Optional[ctk.CTkImage]:
    try:
        base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Config.ICONS_DIR.parent.parent
        icon_path = base_path / "assets/icons" / f"{icon_name}.png"
        
        if icon_path.exists():
            return ctk.CTkImage(Image.open(icon_path), size=size)
        else:
            logger.warning(f"图标文件不存在：{icon_path}")
    except Exception as e:
        logger.warning(f"加载图标失败 {icon_name}：{str(e)}")
    return None

class WelcomePage(ctk.CTkFrame):
    def __init__(
        self, 
        parent: ctk.CTkFrame, 
        new_project_callback: Callable, 
        open_project_callback: Callable,
        open_recent_callback: Callable[[str], None]
    ):
        super().__init__(parent, fg_color=THEME["bg"])
        self.new_project_callback = new_project_callback
        self.open_project_callback = open_project_callback
        self.open_recent_callback = open_recent_callback
        
        title_label = ctk.CTkLabel(self, text="RSTao Remote Sensing Studio", font=FONT_TITLE)
        title_label.pack(pady=(120, 20))
        
        sub_label = ctk.CTkLabel(
            self, 
            text="专业遥感图像处理与分析工具", 
            font=FONT_NORMAL, 
            text_color=THEME["text_secondary"]
        )
        sub_label.pack(pady=10)
        
        btn_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        btn_frame.pack(pady=50, fill="x", padx=Config.UI_CONSTANTS["welcome_padx"])
        
        new_icon = load_icon("new", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            btn_frame, text="新建项目", image=new_icon, compound="left",
            font=FONT_NORMAL, command=self.new_project_callback
        ).pack(fill="x", padx=20, pady=5)
        
        open_icon = load_icon("open", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            btn_frame, text="打开项目", image=open_icon, compound="left",
            font=FONT_NORMAL, command=self.open_project_callback
        ).pack(fill="x", padx=20, pady=5)
        
        sample_icon = load_icon("sample", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            btn_frame, text="加载示例数据", image=sample_icon, compound="left",
            font=FONT_NORMAL
        ).pack(fill="x", padx=20, pady=5)
        
        recent_label = ctk.CTkLabel(self, text="最近打开的项目", font=FONT_SUBTITLE)
        recent_label.pack(pady=(40, 10), anchor="w", padx=Config.UI_CONSTANTS["welcome_padx"])
        
        self.recent_frame = ctk.CTkFrame(self, **PANEL_STYLE)
        self.recent_frame.pack(fill="x", padx=Config.UI_CONSTANTS["welcome_padx"])
        
        self.update_recent_list([])

    def update_recent_list(self, recent_projects: List[str]):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        
        display_projects = recent_projects[:Config.RECENT_PROJECTS_MAX]
        
        if not display_projects:
            ctk.CTkLabel(
                self.recent_frame, 
                text="暂无最近项目", 
                text_color=THEME["text_secondary"]
            ).pack(pady=20)
            return
        
        for path in display_projects:
            path_obj = Path(path)
            if path_obj.exists():
                name = path_obj.stem[:20] + "..." if len(path_obj.stem) > 20 else path_obj.stem
                # 已删除tooltip=path
                btn = ctk.CTkButton(
                    self.recent_frame, text=name, 
                    fg_color="transparent", hover_color=THEME["border"],
                    command=lambda p=path: self.open_recent_callback(p)
                )
                btn.pack(fill="x", padx=10, pady=2)

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
            "image_size": ctk.StringVar(value="无图像"),
            "algorithm": ctk.StringVar(value="就绪"),
            "features": ctk.StringVar(value="0"),
            "zoom": ctk.StringVar(value="100%")
        }
        
        self.feature_tab: Optional[FeatureTab] = None
        self.match_tab: Optional[MatchTab] = None
        self.vector_tab: Optional[VectorTab] = None
        
        self.project_name_label: Optional[ctk.CTkLabel] = None
        self.notebook: Optional[ctk.CTkTabview] = None
        
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
            self.main_container, 
            self.new_project, 
            self.open_project,
            self.open_recent_project
        )
        self.welcome_page.update_recent_list(self.project_manager.recent_projects)
        self.welcome_page.pack(fill="both", expand=True)

    def show_main_interface(self):
        self._clear_main_container()
        
        try:
            self.create_ribbon()
            
            self.notebook = ctk.CTkTabview(self.main_container, corner_radius=8)
            self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            
            self.create_statusbar()
            
            self.init_tabs()
            
            if self.project_manager.current_project:
                project_name = self.project_manager.current_project.get("project_name", "未知项目")
                self.project_name_label.configure(text=f"项目: {project_name}")
                self.restore_project_state()
            
            logger.info("主工作界面初始化完成")
        except Exception as e:
            logger.error("初始化主界面失败", exc_info=True)
            messagebox.showerror("错误", f"界面初始化失败：{str(e)}")
            self.show_welcome()

    def _clear_main_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def _prompt_save_project(self) -> bool:
        if self.project_manager.current_project and self.notebook:
            if messagebox.askyesno("提示", "当前项目未保存，是否保存？"):
                return self.save_project()
        return True

    def create_ribbon(self):
        self.ribbon = ctk.CTkFrame(
            self.main_container, 
            height=Config.UI_CONSTANTS["ribbon_height"], 
            corner_radius=0, 
            fg_color=THEME["panel"]
        )
        self.ribbon.pack(fill="x", padx=10, pady=(10, 0))
        
        file_frame = ctk.CTkFrame(self.ribbon, fg_color="transparent")
        file_frame.pack(side="left", padx=10, pady=10)
        
        new_icon = load_icon("new", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            file_frame, text="新建", image=new_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.new_project
        ).pack(side="left", padx=2)
        
        open_icon = load_icon("open", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            file_frame, text="打开", image=open_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.open_project
        ).pack(side="left", padx=2)
        
        save_icon = load_icon("save", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            file_frame, text="保存", image=save_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.save_project
        ).pack(side="left", padx=2)
        
        export_icon = load_icon("export", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            file_frame, text="导出", image=export_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.export_current
        ).pack(side="left", padx=2)
        
        help_frame = ctk.CTkFrame(self.ribbon, fg_color="transparent")
        help_frame.pack(side="right", padx=10, pady=10)
        
        help_icon = load_icon("help", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            help_frame, text="帮助", image=help_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.show_help
        ).pack(side="left", padx=2)
        
        about_icon = load_icon("about", Config.UI_CONSTANTS["btn_icon_size"])
        ctk.CTkButton(
            help_frame, text="关于", image=about_icon, compound="top",
            width=60, height=40, font=FONT_SMALL, command=self.show_about
        ).pack(side="left", padx=2)

    def create_statusbar(self):
        self.statusbar = ctk.CTkFrame(
            self.main_container, 
            height=Config.UI_CONSTANTS["statusbar_height"], 
            corner_radius=0, 
            fg_color=THEME["panel"]
        )
        self.statusbar.pack(fill="x", padx=10, pady=(0, 10))
        
        self.project_name_label = ctk.CTkLabel(self.statusbar, text="未打开项目", font=FONT_SMALL)
        self.project_name_label.pack(side="left", padx=10)
        self._add_status_separator()
        
        ctk.CTkLabel(self.statusbar, text="就绪", font=FONT_SMALL).pack(side="left", padx=10)
        self._add_status_separator()
        
        status_items = [
            self.status_vars["image_size"],
            self.status_vars["algorithm"],
            self.status_vars["features"],
            self.status_vars["zoom"]
        ]
        
        for var in status_items:
            ctk.CTkLabel(self.statusbar, textvariable=var, font=FONT_SMALL).pack(side="left", padx=10)
            self._add_status_separator()

    def _add_status_separator(self):
        ctk.CTkLabel(
            self.statusbar, 
            text="|", 
            font=FONT_SMALL, 
            text_color=THEME["text_secondary"]
        ).pack(side="left")

    def init_tabs(self):
        try:
            self.feature_tab = FeatureTab(self.notebook.add("特征检测"), self.status_vars)
            self.feature_tab.pack(fill="both", expand=True)
            
            self.match_tab = MatchTab(self.notebook.add("影像匹配"), self.status_vars)
            self.match_tab.pack(fill="both", expand=True)
            
            self.vector_tab = VectorTab(self.notebook.add("矢量编辑"), self.status_vars)
            self.vector_tab.pack(fill="both", expand=True)
        except Exception as e:
            logger.error("初始化标签页失败", exc_info=True)
            messagebox.showerror("错误", f"标签页初始化失败：{str(e)}")

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
            title="保存新项目"
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
            filetypes=[("RSTao项目文件", "*.rstao")],
            title="打开RSTao项目"
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
        
        if not self.notebook:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return
        
        try:
            feature_state = self.feature_tab.get_state() if self.feature_tab else {}
            match_state = self.match_tab.get_state() if self.match_tab else {}
            vector_state = self.vector_tab.get_state() if self.vector_tab else {}
            current_tab = self.notebook.get()
            
            if self.project_manager.save_project(feature_state, match_state, vector_state, current_tab):
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
            title="项目另存为"
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
        if not project or not self.notebook:
            return
        
        try:
            current_tab = project.get("current_tab")
            if current_tab:
                self.notebook.set(current_tab)
            
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
            plt.close('all')
            
            self.quit()
            logger.info("程序正常退出")
        except Exception as e:
            logger.error("关闭窗口时出错", exc_info=True)
            sys.exit(1)

    def export_current(self):
        if not self.notebook:
            messagebox.showwarning("提示", "请先创建或打开一个项目")
            return
        
        cur_tab = self.notebook.get()
        try:
            if cur_tab == "特征检测" and self.feature_tab:
                self.feature_tab.save_result()
            elif cur_tab == "影像匹配" and self.match_tab:
                self.match_tab.save_result()
            elif cur_tab == "矢量编辑" and self.vector_tab:
                self.vector_tab.export_file()
            messagebox.showinfo("成功", "导出成功")
        except Exception as e:
            logger.error(f"导出 {cur_tab} 失败", exc_info=True)
            messagebox.showerror("导出失败", f"导出失败：{str(e)}")

    def show_help(self):
        help_text = """
RSTao Remote Sensing Studio
============================
专业遥感图像处理与分析工具

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