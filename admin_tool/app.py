"""
RSTao-Tool 统一授权管理工具
标签1：离线密钥生成（原key_generator功能）
标签2：在线激活码管理（对接激活服务器API）
标签3：服务器配置
"""

import hashlib
import json
import logging
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from typing import List, Optional

import customtkinter as ctk
import pyperclip
from tkcalendar import DateEntry

# 导入公共加密模块
sys.path.insert(0, str(Path(__file__).parent.parent))


# ====================== 配置 ======================
from .tabs import OfflineKeyTab, OnlineCodeTab


@dataclass
class ToolConfig:
    """全局配置"""

    WINDOW_SIZE: str = "900x650"
    WINDOW_TITLE: str = "RSTao-Tool · 授权管理中心"
    FONT_TITLE: tuple = ("Microsoft YaHei", 18, "bold")
    FONT_SUBTITLE: tuple = ("Microsoft YaHei", 14, "bold")
    FONT_MAIN: tuple = ("Microsoft YaHei", 12)
    FONT_SMALL: tuple = ("Microsoft YaHei", 10)
    FONT_MONO: tuple = ("Consolas", 10)
    BTN_PRIMARY: str = "#2563eb"
    BTN_PRIMARY_HOVER: str = "#1d4ed8"
    BTN_SUCCESS: str = "#10b981"
    BTN_SUCCESS_HOVER: str = "#059669"
    BTN_DANGER: str = "#ef4444"
    BTN_DANGER_HOVER: str = "#dc2626"
    BTN_WARNING: str = "#f59e0b"
    BTN_WARNING_HOVER: str = "#d97706"
    CONFIG_FILE: Path = Path(__file__).parent.parent / ".admin_config.json"


# ====================== 日志 ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AdminTool")


class AdminTool(ctk.CTk):
    """统一授权管理工具"""

    def __init__(self):
        super().__init__()
        self.config = ToolConfig()
        self._server_config = self._load_config()
        # 窗口
        self.title(self.config.WINDOW_TITLE)
        self.geometry(self.config.WINDOW_SIZE)
        self.resizable(True, True)
        self.minsize(800, 550)
        ctk.set_appearance_mode("dark")
        self._center_window()
        # 服务器内嵌
        self._closing = False
        self._server_process = None
        self._server_running = False
        self._server_port = 18080
        self._create_ui()

    # ====================== 配置读写 ======================
    def _load_config(self) -> dict:
        if self.config.CONFIG_FILE.exists():
            try:
                with open(self.config.CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.debug("配置加载失败，使用默认值")
                pass
        return {"server_url": "http://127.0.0.1:18080", "admin_token": ""}

    def _save_config(self):
        try:
            with open(self.config.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._server_config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 900) // 2
        y = (sh - 650) // 2
        self.geometry(f"+{x}+{y}")

    # ====================== API 调用 ======================
    def _api_call(self, method: str, path: str, body: dict = None) -> dict:
        """调用管理 API"""
        url = f"{self._server_config['server_url']}{path}"
        headers = {
            "Authorization": f"Bearer {self._server_config['admin_token']}",
        }
        if method in ("POST", "PUT") and body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {"success": False, "message": f"HTTP {e.code}"}
        except urllib.error.URLError as e:
            return {"success": False, "message": f"连接失败: {e.reason}"}

    # ====================== UI 骨架 ======================
    def _create_ui(self):
        # 标题栏
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 0))
        ctk.CTkLabel(header, text="授权管理中心", font=self.config.FONT_TITLE).pack(side="left")
        # 连接状态
        self._conn_status = ctk.CTkLabel(
            header, text="● 未测试连接", text_color="gray", font=self.config.FONT_SMALL
        )
        self._conn_status.pack(side="right")
        # 标签页
        self.tabview = ctk.CTkTabview(self, corner_radius=10, fg_color="#2b2d31")
        self.tabview.pack(fill="both", expand=True, padx=20, pady=10)
        self.tab_offline = self.tabview.add("离线密钥生成")
        self.tab_online = self.tabview.add("在线激活码管理")
        self.tab_config = self.tabview.add("服务器配置")
        self._offline_tab = OfflineKeyTab(self.tab_offline, self)
        self._offline_tab.build()
        self._online_tab = OnlineCodeTab(self.tab_online, self)
        self._online_tab.build()
        self._build_config_tab()

    # ====================== Tab 1: 离线密钥生成 ======================
    # ====================== Tab 2: 在线激活码管理 ======================
    # ====================== Tab 3: 服务器配置 ======================
    def _build_config_tab(self):
        # --- 内嵌服务器控制 ---
        self._build_server_control(self.tab_config)
        card = ctk.CTkFrame(self.tab_config, corner_radius=10)
        card.pack(fill="x", padx=30, pady=10)
        # 标题
        ctk.CTkLabel(card, text="激活服务器配置", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=20, pady=(15, 5)
        )
        ctk.CTkLabel(
            card,
            text="配置在线激活码管理功能所需的服务器连接信息",
            font=self.config.FONT_SMALL,
            text_color="gray",
        ).pack(anchor="w", padx=20, pady=(0, 10))
        # 服务器地址
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(row1, text="服务器地址", font=self.config.FONT_MAIN, width=100).pack(
            side="left"
        )
        self._server_url_entry = ctk.CTkEntry(row1, font=self.config.FONT_MAIN, height=36)
        self._server_url_entry.pack(side="left", fill="x", expand=True)
        self._server_url_entry.insert(
            0, self._server_config.get("server_url", "http://127.0.0.1:18080")
        )
        # 管理员令牌
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(row2, text="管理员令牌", font=self.config.FONT_MAIN, width=100).pack(
            side="left"
        )
        self._token_entry = ctk.CTkEntry(
            row2, font=("Consolas", 11), height=36, placeholder_text="首次使用请点击获取令牌"
        )
        self._token_entry.pack(side="left", fill="x", expand=True)
        if self._server_config.get("admin_token"):
            self._token_entry.insert(0, self._server_config["admin_token"])
        # 提示
        ctk.CTkLabel(
            card,
            text="⚠ 令牌具有完全管理权限，请妥善保管",
            font=self.config.FONT_SMALL,
            text_color="#f59e0b",
        ).pack(anchor="w", padx=20, pady=(5, 0))
        # 按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(
            btn_row,
            text="获取令牌",
            command=self._get_admin_token,
            fg_color=self.config.BTN_WARNING,
            hover_color=self.config.BTN_WARNING_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row,
            text="测试连接",
            command=self._test_connection,
            fg_color=self.config.BTN_PRIMARY,
            hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row,
            text="保存配置",
            command=self._save_server_config,
            fg_color=self.config.BTN_SUCCESS,
            hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
        ).pack(side="left", padx=5)

    # ====================== 内嵌服务器控制 ======================
    def _build_server_control(self, parent):
        """构建内嵌服务器控制面板"""
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", padx=30, pady=5)
        # 标题行
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text="本机激活服务器", font=self.config.FONT_SUBTITLE).pack(
            side="left"
        )
        self._server_status_label = ctk.CTkLabel(
            header, text="● 未启动", text_color="gray", font=self.config.FONT_MAIN
        )
        self._server_status_label.pack(side="right")
        # 说明
        ctk.CTkLabel(
            card,
            text="内置激活服务器，无需单独启动。开启后即可使用在线激活码管理功能。",
            font=self.config.FONT_SMALL,
            text_color="gray",
        ).pack(anchor="w", padx=20, pady=(0, 5))
        # 端口
        port_row = ctk.CTkFrame(card, fg_color="transparent")
        port_row.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(port_row, text="监听端口", font=self.config.FONT_MAIN, width=80).pack(
            side="left"
        )
        self._server_port_entry = ctk.CTkEntry(port_row, width=80, font=self.config.FONT_MAIN)
        self._server_port_entry.pack(side="left")
        self._server_port_entry.insert(0, str(self._server_port))
        # 开机自启
        self._auto_start_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            port_row,
            text="启动工具时自动开启服务器",
            variable=self._auto_start_var,
            font=self.config.FONT_SMALL,
        ).pack(side="left", padx=20)
        # 日志输出
        self._server_log = ctk.CTkTextbox(
            card, height=100, wrap="word", font=("Consolas", 10), fg_color="#1a1b1e"
        )
        self._server_log.pack(fill="x", padx=20, pady=(5, 5))
        self._server_log.insert("end", "就绪，点击「启动服务器」开始。\n")
        self._server_log.configure(state="disabled")
        # 按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))
        self._btn_start_server = ctk.CTkButton(
            btn_row,
            text="启动服务器",
            command=self._start_server,
            fg_color=self.config.BTN_SUCCESS,
            hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
        )
        self._btn_start_server.pack(side="left", padx=5)
        self._btn_stop_server = ctk.CTkButton(
            btn_row,
            text="停止服务器",
            command=self._stop_server,
            fg_color=self.config.BTN_DANGER,
            hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
            state="disabled",
        )
        self._btn_stop_server.pack(side="left", padx=5)

    def _start_server(self):
        """启动内嵌激活服务器（后台启动 + HTTP健康检查）"""
        if self._server_running:
            messagebox.showinfo("提示", "服务器已在运行中")
            return

        self._server_port = int(self._server_port_entry.get().strip() or "18080")
        server_script = str(Path(__file__).parent.parent / "server" / "activation_server.py")
        # Fallback path if server script is in _admin_repo
        if not Path(server_script).exists():
            alt_path = str(
                Path(__file__).parent.parent / "_admin_repo" / "server" / "activation_server.py"
            )
            if Path(alt_path).exists():
                server_script = alt_path

        if not Path(server_script).exists():
            messagebox.showerror("错误", f"找不到服务器脚本: {server_script}")
            return

        self._append_server_log(f"正在启动服务器 (端口 {self._server_port})...\n")
        self._btn_start_server.configure(state="disabled", text="启动中...")

        # 直接启动子进程，不读stdout
        try:
            self._server_process = subprocess.Popen(
                [sys.executable, server_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as e:
            self._append_server_log(f"启动失败: {e}\n")
            self._btn_start_server.configure(state="normal", text="启动服务器")
            messagebox.showerror("错误", f"启动失败: {e}")
            return

        # 后台线程轮询 HTTP 健康检查
        def _wait_ready():
            deadline = time.time() + 8
            while time.time() < deadline:
                time.sleep(0.5)
                if self._server_process.poll() is not None:
                    if not self._closing:
                        self.after(0, self._stop_server)
                    self.after(
                        0,
                        lambda: (
                            not self._closing
                            and self._append_server_log("服务器进程已退出，启动失败。\n")
                        ),
                    )
                    self.after(
                        0,
                        lambda: self._btn_start_server.configure(state="normal", text="启动服务器"),
                    )
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "失败", "服务器启动失败，请检查端口是否被占用。"
                        ),
                    )
                    return
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{self._server_port}/api/health", method="GET"
                    )
                    urllib.request.urlopen(req, timeout=2)
                    # 成功
                    self._server_running = True
                    self.after(
                        0,
                        lambda: self._server_status_label.configure(
                            text="● 运行中", text_color="#10b981"
                        ),
                    )
                    self.after(
                        0,
                        lambda: self._btn_start_server.configure(
                            state="disabled", text="启动服务器"
                        ),
                    )
                    self.after(
                        0,
                        lambda: not self._closing
                        and self._btn_stop_server.configure(state="normal"),
                    )
                    self.after(
                        0,
                        lambda: self._append_server_log(
                            f"服务器启动成功！ http://localhost:{self._server_port}\n"
                        ),
                    )
                    # 自动获取令牌
                    self._try_auto_token()
                    return
                except Exception:
                    continue
            # 超时
            self.after(
                0,
                lambda: (
                    not self._closing
                    and self._append_server_log("启动超时，请检查端口或防火墙。\n")
                ),
            )
            self.after(
                0, lambda: self._btn_start_server.configure(state="normal", text="启动服务器")
            )
            self.after(
                0, lambda: messagebox.showerror("超时", "服务器启动超时，请检查端口是否被占用。")
            )

        threading.Thread(target=_wait_ready, daemon=True).start()

    def _try_auto_token(self):
        """如果还没有令牌，自动尝试获取"""
        if self._server_config.get("admin_token"):
            return
        try:
            url = f"http://127.0.0.1:{self._server_port}/api/admin/token"
            req = urllib.request.Request(
                url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                token = result["token"]
                self._token_entry.delete(0, "end")
                self._token_entry.insert(0, token)
                self._server_config["admin_token"] = token
                self._append_server_log(f"令牌已自动获取并保存\n")
                self._save_config()
                self._conn_status.configure(text="● 已连接", text_color="#10b981")
                self.after(100, self._online_tab._refresh_online_data)
        except Exception:
            pass

    def _stop_server(self):
        """停止内嵌服务器"""
        if self._server_process:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                try:
                    self._server_process.kill()
                except Exception:
                    pass
            self._server_process = None
        self._server_running = False
        if not self._closing:
            try:
                self._server_status_label.configure(text="● 已停止", text_color="gray")
                self._btn_start_server.configure(state="normal")
                self._btn_stop_server.configure(state="disabled")
                self._append_server_log("服务器已停止。\n")
            except Exception:
                pass

    def _append_server_log(self, text):
        """向服务器日志区追加文本"""
        if self._closing:
            return
        try:
            self._server_log.configure(state="normal")
            self._server_log.insert("end", text)
            self._server_log.see("end")
            self._server_log.configure(state="disabled")
        except Exception:
            pass

    def _get_admin_token(self):
        """获取管理员令牌"""
        url = f"{self._server_url_entry.get().strip()}/api/admin/token"
        try:
            req = urllib.request.Request(
                url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                token = result["token"]
                self._token_entry.delete(0, "end")
                self._token_entry.insert(0, token)
                pyperclip.copy(token)
                messagebox.showinfo("成功", f"令牌已生成并复制到剪贴板\n请妥善保管！")
            else:
                messagebox.showerror("失败", result.get("message", "获取失败"))
        except Exception as e:
            messagebox.showerror("错误", f"无法连接服务器: {e}")

    def _test_connection(self):
        url = self._server_url_entry.get().strip()
        token = self._token_entry.get().strip()
        try:
            req = urllib.request.Request(
                f"{url}/api/admin/codes", headers={"Authorization": f"Bearer {token}"}, method="GET"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            if "codes" in result or "success" in result:
                self._conn_status.configure(text="● 已连接", text_color="#10b981")
                messagebox.showinfo("成功", "服务器连接正常，鉴权通过！")
            else:
                self._conn_status.configure(text="● 鉴权失败", text_color="#ef4444")
                messagebox.showerror("失败", result.get("message", "未知错误"))
        except urllib.error.HTTPError as e:
            self._conn_status.configure(text="● 鉴权失败", text_color="#ef4444")
            messagebox.showerror("失败", f"HTTP {e.code}: 令牌可能无效")
        except Exception as e:
            self._conn_status.configure(text="● 无法连接", text_color="#ef4444")
            messagebox.showerror("失败", f"无法连接服务器: {e}")

    def _save_server_config(self):
        self._server_config["server_url"] = self._server_url_entry.get().strip()
        self._server_config["admin_token"] = self._token_entry.get().strip()
        self._save_config()
        messagebox.showinfo("成功", "服务器配置已保存")

    # ====================== 入口 ======================
    def run(self):
        # 自动启动
        if self._auto_start_var.get():
            self.after(500, self._start_server)
        self.mainloop()

    def destroy(self):
        self._closing = True
        super().destroy()
