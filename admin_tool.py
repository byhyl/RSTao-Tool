"""
RSTao-Tool 统一授权管理工具
标签1：离线密钥生成（原key_generator功能）
标签2：在线激活码管理（对接激活服务器API）
标签3：服务器配置
"""
import base64
import hashlib
import json
import logging
import sys
import time
import urllib.request
import urllib.error
import threading
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import pyperclip
import customtkinter as ctk
from tkcalendar import DateEntry
from tkinter import messagebox, ttk
# 导入公共加密模块
sys.path.insert(0, str(Path(__file__).parent))
from common.crypto import aes_gcm_encrypt
# ====================== 配置 ======================
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
    CONFIG_FILE: Path = Path(__file__).parent / ".admin_config.json"
# ====================== 日志 ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
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
        data = json.dumps(body).encode() if body else b"{}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._server_config['admin_token']}"
        }
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
            header, text="● 未测试连接", text_color="gray",
            font=self.config.FONT_SMALL
        )
        self._conn_status.pack(side="right")
        # 标签页
        self.tabview = ctk.CTkTabview(
            self, corner_radius=10,
            fg_color="#2b2d31"
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=10)
        self.tab_offline = self.tabview.add("离线密钥生成")
        self.tab_online = self.tabview.add("在线激活码管理")
        self.tab_config = self.tabview.add("服务器配置")
        self._build_offline_tab()
        self._build_online_tab()
        self._build_config_tab()
    # ====================== Tab 1: 离线密钥生成 ======================
    def _build_offline_tab(self):
        self.license_type = "永久授权"
        # 滚动容器
        scroll = ctk.CTkScrollableFrame(self.tab_offline, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=10)
        # 机器码
        card1 = ctk.CTkFrame(scroll, corner_radius=10)
        card1.pack(fill="x", pady=5)
        ctk.CTkLabel(card1, text="用户机器码", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        self._machine_entry = ctk.CTkEntry(
            card1, height=36, placeholder_text="请输入用户提供的机器码（16位MD5）",
            font=self.config.FONT_MAIN
        )
        self._machine_entry.pack(fill="x", padx=15, pady=(5, 10))
        # 授权类型
        card2 = ctk.CTkFrame(scroll, corner_radius=10)
        card2.pack(fill="x", pady=5)
        ctk.CTkLabel(card2, text="授权类型", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        type_row = ctk.CTkFrame(card2, fg_color="transparent")
        type_row.pack(fill="x", padx=15, pady=5)
        self._type_option = ctk.CTkOptionMenu(
            type_row, values=["永久授权", "按天数授权", "指定日期过期"],
            command=self._on_license_type_change,
            font=self.config.FONT_MAIN, width=160
        )
        self._type_option.pack(side="left")
        self._type_option.set("永久授权")
        # 动态参数
        self._offline_param_frame = ctk.CTkFrame(card2, fg_color="transparent")
        self._offline_param_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._day_label = ctk.CTkLabel(self._offline_param_frame, text="授权天数", font=self.config.FONT_MAIN)
        self._day_entry = ctk.CTkEntry(self._offline_param_frame, width=120, placeholder_text=">=1", font=self.config.FONT_MAIN)
        self._date_label = ctk.CTkLabel(self._offline_param_frame, text="过期日期", font=self.config.FONT_MAIN)
        self._date_picker = DateEntry(
            self._offline_param_frame, width=18, background="darkblue",
            foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd",
            font=("Arial", 12), locale="zh_CN"
        )
        # 密钥输出
        card3 = ctk.CTkFrame(scroll, corner_radius=10)
        card3.pack(fill="x", pady=5)
        ctk.CTkLabel(card3, text="生成的密钥", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        self._offline_key_output = ctk.CTkTextbox(
            card3, height=50, wrap="word", font=self.config.FONT_MONO
        )
        self._offline_key_output.pack(fill="x", padx=15, pady=(5, 5))
        self._offline_key_output.configure(state="disabled")
        # 按钮
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(
            btn_row, text="生成密钥", command=self._generate_offline_key,
            fg_color=self.config.BTN_PRIMARY, hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN, width=130
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="复制密钥", command=self._copy_offline_key,
            fg_color=self.config.BTN_SUCCESS, hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN, width=130
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="清空", command=lambda: self._offline_key_output.configure(state="normal") or self._offline_key_output.delete(1.0, "end") or self._offline_key_output.configure(state="disabled"),
            fg_color="transparent", hover_color="#3d4045",
            font=self.config.FONT_MAIN, width=80, border_width=1, border_color="#3d4045"
        ).pack(side="left", padx=5)
    def _on_license_type_change(self, choice):
        self.license_type = choice
        for w in self._offline_param_frame.winfo_children():
            w.pack_forget()
        if choice == "按天数授权":
            self._day_label.pack(side="left", padx=5)
            self._day_entry.pack(side="left", padx=5)
        elif choice == "指定日期过期":
            self._date_label.pack(side="left", padx=5)
            self._date_picker.pack(side="left", padx=5)
    def _generate_offline_key(self):
        machine = self._machine_entry.get().strip()
        if not machine:
            messagebox.showerror("错误", "请输入用户机器码")
            return
        if machine != "UNKNOWN":
            if len(machine) != 16:
                if not messagebox.askyesno("警告", "机器码长度非16位，继续生成？"):
                    return
            try:
                int(machine, 16)
            except ValueError:
                messagebox.showerror("错误", "机器码格式无效")
                return
        try:
            if self.license_type == "永久授权":
                expire_dt = datetime(2099, 12, 31)
            elif self.license_type == "按天数授权":
                days = int(self._day_entry.get().strip() or "0")
                if days <= 0:
                    raise ValueError("天数必须大于0")
                expire_dt = datetime.now() + timedelta(days=days)
            else:
                date_str = self._date_picker.get_date().strftime("%Y-%m-%d")
                expire_dt = datetime.strptime(date_str, "%Y-%m-%d")
                if expire_dt < datetime.now():
                    raise ValueError("过期日期不能早于当前日期")
            auth_str = f"{machine}|{expire_dt.timestamp()}"
            license_key = aes_gcm_encrypt(auth_str)
            if not license_key:
                raise RuntimeError("加密失败")
            self._offline_key_output.configure(state="normal")
            self._offline_key_output.delete(1.0, "end")
            self._offline_key_output.insert("end", license_key)
            self._offline_key_output.configure(state="disabled")
            logger.info(f"离线密钥生成: {machine[:8]}... -> {expire_dt.strftime('%Y-%m-%d')}")
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
        except Exception as e:
            messagebox.showerror("错误", f"生成失败: {e}")
    def _copy_offline_key(self):
        key = self._offline_key_output.get(1.0, "end-1c").strip()
        if not key:
            messagebox.showwarning("提示", "没有可复制的密钥")
            return
        try:
            pyperclip.copy(key)
            messagebox.showinfo("成功", "密钥已复制到剪贴板")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")
    # ====================== Tab 2: 在线激活码管理 ======================
    def _build_online_tab(self):
        # 左右分栏
        self.tab_online.grid_rowconfigure(0, weight=1)
        self.tab_online.grid_columnconfigure(0, weight=0, minsize=380)
        self.tab_online.grid_columnconfigure(1, weight=1)
        # === 左侧：操作面板 ===
        left = ctk.CTkScrollableFrame(self.tab_online, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        # 生成激活码
        card = ctk.CTkFrame(left, corner_radius=10)
        card.pack(fill="x", pady=5)
        ctk.CTkLabel(card, text="生成激活码", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        # 类型
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row1, text="类型", font=self.config.FONT_SMALL, width=80).pack(side="left")
        self._online_type = ctk.CTkOptionMenu(
            row1, values=["permanent", "days", "date"],
            command=self._on_online_type_change,
            font=self.config.FONT_SMALL, width=140
        )
        self._online_type.pack(side="left")
        self._online_type.set("permanent")
        # 次数
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row2, text="可激活次数", font=self.config.FONT_SMALL, width=80).pack(side="left")
        self._online_max = ctk.CTkEntry(row2, width=80, placeholder_text="1", font=self.config.FONT_SMALL)
        self._online_max.pack(side="left")
        self._online_max.insert(0, "1")
        # 动态参数
        self._online_param_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._online_param_frame.pack(fill="x", padx=15, pady=5)
        self._online_days_label = ctk.CTkLabel(self._online_param_frame, text="天数", font=self.config.FONT_SMALL)
        self._online_days_entry = ctk.CTkEntry(self._online_param_frame, width=80, placeholder_text="365", font=self.config.FONT_SMALL)
        self._online_date_label = ctk.CTkLabel(self._online_param_frame, text="截止日期", font=self.config.FONT_SMALL)
        self._online_date_picker = DateEntry(
            self._online_param_frame, width=16, background="darkblue",
            foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd",
            font=("Arial", 10), locale="zh_CN"
        )
        # 备注
        row4 = ctk.CTkFrame(card, fg_color="transparent")
        row4.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row4, text="备注", font=self.config.FONT_SMALL, width=80).pack(side="left")
        self._online_notes = ctk.CTkEntry(row4, placeholder_text="客户名称/用途", font=self.config.FONT_SMALL)
        self._online_notes.pack(side="left", fill="x", expand=True)
        # 按钮
        ctk.CTkButton(
            card, text="生成激活码", command=self._generate_online_code,
            fg_color=self.config.BTN_PRIMARY, hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN, height=36
        ).pack(fill="x", padx=15, pady=10)
        # 生成结果
        result_card = ctk.CTkFrame(left, corner_radius=10)
        result_card.pack(fill="x", pady=5)
        ctk.CTkLabel(result_card, text="最近生成", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        self._online_result = ctk.CTkTextbox(
            result_card, height=100, wrap="word",
            font=self.config.FONT_MONO
        )
        self._online_result.pack(fill="x", padx=15, pady=(5, 5))
        ctk.CTkButton(
            result_card, text="复制激活码", command=self._copy_online_code,
            fg_color=self.config.BTN_SUCCESS, hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_SMALL, height=30
        ).pack(fill="x", padx=15, pady=(0, 10))
        # 刷新按钮
        ctk.CTkButton(
            left, text="刷新列表", command=self._refresh_online_data,
            fg_color="transparent", hover_color="#3d4045",
            font=self.config.FONT_SMALL, border_width=1, border_color="#3d4045"
        ).pack(fill="x", pady=5)
        # 黑名单管理
        bl_card = ctk.CTkFrame(left, corner_radius=10)
        bl_card.pack(fill="x", pady=5)
        ctk.CTkLabel(bl_card, text="黑名单管理", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=15, pady=(10, 0))
        bl_row = ctk.CTkFrame(bl_card, fg_color="transparent")
        bl_row.pack(fill="x", padx=15, pady=5)
        self._bl_entry = ctk.CTkEntry(bl_row, placeholder_text="设备指纹/激活码", font=self.config.FONT_SMALL)
        self._bl_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        bl_btn_row = ctk.CTkFrame(bl_card, fg_color="transparent")
        bl_btn_row.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkButton(
            bl_btn_row, text="加入黑名单", command=lambda: self._blacklist("add"),
            fg_color=self.config.BTN_DANGER, hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_SMALL, height=30
        ).pack(side="left", padx=2, fill="x", expand=True)
        ctk.CTkButton(
            bl_btn_row, text="移除", command=lambda: self._blacklist("remove"),
            fg_color=self.config.BTN_WARNING, hover_color=self.config.BTN_WARNING_HOVER,
            font=self.config.FONT_SMALL, height=30
        ).pack(side="left", padx=2, fill="x", expand=True)
        # === 右侧：数据展示 ===
        right = ctk.CTkFrame(self.tab_online, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        # 子标签（激活码列表 / 激活记录 / 黑名单）
        self._sub_tab = ctk.CTkTabview(right, corner_radius=8)
        self._sub_tab.pack(fill="both", expand=True, padx=5, pady=5)
        self._tab_codes = self._sub_tab.add("激活码列表")
        self._tab_records = self._sub_tab.add("激活记录")
        self._tab_blacklist = self._sub_tab.add("黑名单")
        self._build_code_list()
        self._build_record_list()
        self._build_blacklist_view()
    def _build_code_list(self):
        self._code_text = ctk.CTkTextbox(self._tab_codes, wrap="none", font=self.config.FONT_MONO)
        self._code_text.pack(fill="both", expand=True, padx=5, pady=5)
        btn_row = ctk.CTkFrame(self._tab_codes, fg_color="transparent")
        btn_row.pack(fill="x", padx=5, pady=(0, 5))
        ctk.CTkButton(
            btn_row, text="作废选中", command=self._revoke_code,
            fg_color=self.config.BTN_DANGER, hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_SMALL, height=28
        ).pack(side="left", padx=2)
    def _build_record_list(self):
        self._record_text = ctk.CTkTextbox(self._tab_records, wrap="none", font=self.config.FONT_MONO)
        self._record_text.pack(fill="both", expand=True, padx=5, pady=5)
    def _build_blacklist_view(self):
        self._blacklist_text = ctk.CTkTextbox(self._tab_blacklist, wrap="none", font=self.config.FONT_MONO)
        self._blacklist_text.pack(fill="both", expand=True, padx=5, pady=5)
    def _on_online_type_change(self, choice):
        for w in self._online_param_frame.winfo_children():
            w.pack_forget()
        if choice == "days":
            self._online_days_label.pack(side="left", padx=3)
            self._online_days_entry.pack(side="left", padx=3)
        elif choice == "date":
            self._online_date_label.pack(side="left", padx=3)
            self._online_date_picker.pack(side="left", padx=3)
    def _generate_online_code(self):
        body = {
            "license_type": self._online_type.get(),
            "max_activations": int(self._online_max.get().strip() or "1"),
            "notes": self._online_notes.get().strip()
        }
        if body["license_type"] == "days":
            body["expire_days"] = int(self._online_days_entry.get().strip() or "365")
        elif body["license_type"] == "date":
            body["expire_date"] = self._online_date_picker.get_date().strftime("%Y-%m-%d")
        result = self._api_call("POST", "/api/admin/generate", body)
        if result.get("success"):
            code = result["code"]
            self._online_result.delete(1.0, "end")
            self._online_result.insert("end", f"激活码: {code}\n")
            self._online_result.insert("end", f"类型: {body['license_type']} | 最大次数: {body['max_activations']}\n")
            if body.get("notes"):
                self._online_result.insert("end", f"备注: {body['notes']}\n")
            pyperclip.copy(code)
            messagebox.showinfo("成功", f"激活码已生成并复制到剪贴板:\n{code}")
            self._refresh_online_data()
        else:
            messagebox.showerror("失败", result.get("message", "未知错误"))
    def _copy_online_code(self):
        text = self._online_result.get(1.0, "end-1c").strip()
        if not text:
            messagebox.showwarning("提示", "没有可复制的激活码")
            return
        # 提取激活码
        for line in text.split("\n"):
            if line.startswith("激活码:"):
                code = line.split(":", 1)[1].strip()
                pyperclip.copy(code)
                messagebox.showinfo("成功", f"已复制: {code}")
                return
        messagebox.showwarning("提示", "未找到激活码")
    def _revoke_code(self):
        # 简单的弹窗输入
        dialog = ctk.CTkInputDialog(
            text="输入要作废的激活码：",
            title="作废激活码",
            font=self.config.FONT_MAIN
        )
        code = dialog.get_input()
        if not code:
            return
        result = self._api_call("POST", "/api/admin/revoke", {"code": code.strip()})
        if result.get("success"):
            messagebox.showinfo("成功", f"激活码 {code} 已作废")
            self._refresh_online_data()
        else:
            messagebox.showerror("失败", result.get("message", "操作失败"))
    def _blacklist(self, action):
        identifier = self._bl_entry.get().strip()
        if not identifier:
            messagebox.showwarning("提示", "请输入设备指纹或激活码")
            return
        result = self._api_call("POST", "/api/admin/blacklist", {
            "action": action,
            "identifier": identifier,
            "reason": "管理员操作"
        })
        if result.get("success"):
            messagebox.showinfo("成功", result["message"])
            self._refresh_online_data()
        else:
            messagebox.showerror("失败", result.get("message", "操作失败"))
    def _refresh_online_data(self):
        """刷新所有在线数据"""
        # 激活码列表
        codes = self._api_call("GET", "/api/admin/codes")
        self._code_text.delete(1.0, "end")
        if codes.get("codes"):
            header = f"{'激活码':<18} {'类型':<12} {'次数':<8} {'状态':<8} {'备注'}\n"
            sep = "-" * 80 + "\n"
            self._code_text.insert("end", header)
            self._code_text.insert("end", sep)
            for c in codes["codes"]:
                status = "有效" if c.get("is_active") else "已作废"
                color = "🟢" if c.get("is_active") else "🔴"
                notes = c.get("notes", "")[:20]
                self._code_text.insert("end",
                    f"{color} {c['code']:<16} {c['license_type']:<12} "
                    f"{c['current_activations']}/{c['max_activations']:<6} {status:<8} {notes}\n"
                )
        else:
            self._code_text.insert("end", f"加载失败: {codes.get('message', '未连接服务器')}")
        # 激活记录
        records = self._api_call("GET", "/api/admin/records")
        self._record_text.delete(1.0, "end")
        if records.get("records"):
            header = f"{'时间':<20} {'激活码':<18} {'设备指纹'}\n"
            self._record_text.insert("end", header)
            self._record_text.insert("end", "-" * 80 + "\n")
            for r in records["records"]:
                fp = r.get("device_fingerprint", "")[:30]
                self._record_text.insert("end",
                    f"{r['activated_at']:<20} {r['activation_code']:<18} {fp}\n"
                )
        else:
            self._record_text.insert("end", f"加载失败: {records.get('message', '未连接服务器')}")
        # 黑名单
        bl = self._api_call("GET", "/api/admin/blacklist")
        self._blacklist_text.delete(1.0, "end")
        if bl.get("blacklist"):
            for b in bl["blacklist"]:
                self._blacklist_text.insert("end",
                    f"🚫 {b['identifier']:<40} {b.get('reason','')}\n"
                )
        else:
            self._blacklist_text.insert("end", f"黑名单为空 ({bl.get('message','')})")
    # ====================== Tab 3: 服务器配置 ======================
    def _build_config_tab(self):
        # --- 内嵌服务器控制 ---
        self._build_server_control(self.tab_config)
        card = ctk.CTkFrame(self.tab_config, corner_radius=10)
        card.pack(fill="x", padx=30, pady=10)
        # 标题
        ctk.CTkLabel(card, text="激活服务器配置", font=self.config.FONT_SUBTITLE).pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkLabel(card, text="配置在线激活码管理功能所需的服务器连接信息",
                     font=self.config.FONT_SMALL, text_color="gray").pack(anchor="w", padx=20, pady=(0, 10))
        # 服务器地址
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(row1, text="服务器地址", font=self.config.FONT_MAIN, width=100).pack(side="left")
        self._server_url_entry = ctk.CTkEntry(
            row1, font=self.config.FONT_MAIN, height=36
        )
        self._server_url_entry.pack(side="left", fill="x", expand=True)
        self._server_url_entry.insert(0, self._server_config.get("server_url", "http://127.0.0.1:18080"))
        # 管理员令牌
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(row2, text="管理员令牌", font=self.config.FONT_MAIN, width=100).pack(side="left")
        self._token_entry = ctk.CTkEntry(
            row2, font=("Consolas", 11), height=36,
            placeholder_text="首次使用请点击获取令牌"
        )
        self._token_entry.pack(side="left", fill="x", expand=True)
        if self._server_config.get("admin_token"):
            self._token_entry.insert(0, self._server_config["admin_token"])
        # 提示
        ctk.CTkLabel(card, text="⚠ 令牌具有完全管理权限，请妥善保管",
                     font=self.config.FONT_SMALL, text_color="#f59e0b").pack(anchor="w", padx=20, pady=(5, 0))
        # 按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(
            btn_row, text="获取令牌", command=self._get_admin_token,
            fg_color=self.config.BTN_WARNING, hover_color=self.config.BTN_WARNING_HOVER,
            font=self.config.FONT_MAIN, height=36
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="测试连接", command=self._test_connection,
            fg_color=self.config.BTN_PRIMARY, hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN, height=36
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="保存配置", command=self._save_server_config,
            fg_color=self.config.BTN_SUCCESS, hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN, height=36
        ).pack(side="left", padx=5)
    # ====================== 内嵌服务器控制 ======================
    def _build_server_control(self, parent):
        """构建内嵌服务器控制面板"""
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", padx=30, pady=5)
        # 标题行
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text="本机激活服务器", font=self.config.FONT_SUBTITLE).pack(side="left")
        self._server_status_label = ctk.CTkLabel(
            header, text="● 未启动", text_color="gray",
            font=self.config.FONT_MAIN
        )
        self._server_status_label.pack(side="right")
        # 说明
        ctk.CTkLabel(card, text="内置激活服务器，无需单独启动。开启后即可使用在线激活码管理功能。",
                     font=self.config.FONT_SMALL, text_color="gray").pack(anchor="w", padx=20, pady=(0, 5))
        # 端口
        port_row = ctk.CTkFrame(card, fg_color="transparent")
        port_row.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(port_row, text="监听端口", font=self.config.FONT_MAIN, width=80).pack(side="left")
        self._server_port_entry = ctk.CTkEntry(
            port_row, width=80, font=self.config.FONT_MAIN
        )
        self._server_port_entry.pack(side="left")
        self._server_port_entry.insert(0, str(self._server_port))
        # 开机自启
        self._auto_start_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            port_row, text="启动工具时自动开启服务器",
            variable=self._auto_start_var, font=self.config.FONT_SMALL
        ).pack(side="left", padx=20)
        # 日志输出
        self._server_log = ctk.CTkTextbox(
            card, height=100, wrap="word",
            font=("Consolas", 10), fg_color="#1a1b1e"
        )
        self._server_log.pack(fill="x", padx=20, pady=(5, 5))
        self._server_log.insert("end", "就绪，点击「启动服务器」开始。\n")
        self._server_log.configure(state="disabled")
        # 按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))
        self._btn_start_server = ctk.CTkButton(
            btn_row, text="启动服务器", command=self._start_server,
            fg_color=self.config.BTN_SUCCESS, hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN, height=36
        )
        self._btn_start_server.pack(side="left", padx=5)
        self._btn_stop_server = ctk.CTkButton(
            btn_row, text="停止服务器", command=self._stop_server,
            fg_color=self.config.BTN_DANGER, hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_MAIN, height=36, state="disabled"
        )
        self._btn_stop_server.pack(side="left", padx=5)
    def _start_server(self):
        """启动内嵌激活服务器（后台启动 + HTTP健康检查）"""
        if self._server_running:
            messagebox.showinfo("提示", "服务器已在运行中")
            return

        self._server_port = int(self._server_port_entry.get().strip() or "18080")
        server_script = str(Path(__file__).parent / "server" / "activation_server.py")

        if not Path(server_script).exists():
            messagebox.showerror("错误", f"找不到服务器脚本: {server_script}")
            return

        self._append_server_log(f"正在启动服务器 (端口 {self._server_port})...\n")
        self._btn_start_server.configure(state="disabled", text="启动中...")

        # 直接启动子进程，不读stdout
        try:
            self._server_process = subprocess.Popen(
                [sys.executable, server_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
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
                    self.after(0, lambda: not self._closing and self._stop_server())
                    self.after(0, lambda: self._append_server_log("服务器进程已退出，启动失败。\n"))
                    self.after(0, lambda: self._btn_start_server.configure(state="normal", text="启动服务器"))
                    self.after(0, lambda: messagebox.showerror("失败", "服务器启动失败，请检查端口是否被占用。"))
                    return
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{self._server_port}/api/health", method="GET")
                    urllib.request.urlopen(req, timeout=2)
                    # 成功
                    self._server_running = True
                    self.after(0, lambda: self._server_status_label.configure(text="● 运行中", text_color="#10b981"))
                    self.after(0, lambda: self._btn_start_server.configure(state="disabled", text="启动服务器"))
                    self.after(0, lambda: self._btn_stop_server.configure(state="normal"))
                    self.after(0, lambda: self._append_server_log(f"服务器启动成功！ http://localhost:{self._server_port}\n"))
                    # 自动获取令牌
                    self._try_auto_token()
                    return
                except Exception:
                    continue
            # 超时
            self.after(0, lambda: self._append_server_log("启动超时，请检查端口或防火墙。\n"))
            self.after(0, lambda: self._btn_start_server.configure(state="normal", text="启动服务器"))
            self.after(0, lambda: messagebox.showerror("超时", "服务器启动超时，请检查端口是否被占用。"))

        threading.Thread(target=_wait_ready, daemon=True).start()

    def _try_auto_token(self):
        """如果还没有令牌，自动尝试获取"""
        if self._server_config.get("admin_token"):
            return
        try:
            url = f"http://127.0.0.1:{self._server_port}/api/admin/token"
            req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
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
                self.after(100, self._refresh_online_data)
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
            req = urllib.request.Request(url, data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
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
                f"{url}/api/admin/codes",
                headers={"Authorization": f"Bearer {token}"},
                method="GET"
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
if __name__ == "__main__":
    try:
        app = AdminTool()
        app.run()
    except Exception as e:
        logger.critical("管理工具启动失败", exc_info=True)
        messagebox.showerror("致命错误", f"启动失败: {e}")
        sys.exit(1)