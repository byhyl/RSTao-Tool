"""激活界面模块 — ActivationUI（依赖 AuthManager，不依赖主程序）"""

import sys
import threading
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from auth import AuthConfig, AuthManager


class ActivationUI:
    """激活界面"""

    def __init__(self, auth_manager: AuthManager, on_activated: Callable[[], None]):
        self.auth_manager = auth_manager
        self.config = auth_manager.config
        self._on_activated = on_activated
        self.root = ctk.CTk()
        self._init_window()
        self._create_ui()

    def _init_window(self):
        self.root.title(self.config.ACTIVATION_WINDOW_TITLE)
        self.root.geometry(self.config.ACTIVATION_WINDOW_SIZE)
        self.root.resizable(False, False)
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.root.winfo_width()) // 2
        y = (sh - self.root.winfo_height()) // 2
        self.root.geometry(f"+{x}+{y}")

    def _create_ui(self):
        # 机器码显示
        ctk.CTkLabel(self.root, text="本机机器码", font=self.config.FONT_MAIN).pack(pady=5)
        machine_code = self.auth_manager.get_machine_code()
        machine_var = ctk.StringVar(value=machine_code)
        ctk.CTkEntry(
            self.root,
            width=400,
            state="readonly",
            textvariable=machine_var,
            font=self.config.FONT_SMALL,
        ).pack(pady=2)

        # 激活方式选择
        ctk.CTkLabel(self.root, text="激活方式", font=self.config.FONT_MAIN).pack(pady=5)
        self.activate_mode = ctk.StringVar(value="license_key")
        mode_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        mode_frame.pack(pady=2)
        ctk.CTkRadioButton(
            mode_frame,
            text="授权密钥激活",
            variable=self.activate_mode,
            value="license_key",
            font=self.config.FONT_SMALL,
            command=self._on_mode_change,
        ).pack(side="left", padx=10)
        ctk.CTkRadioButton(
            mode_frame,
            text="在线激活码激活",
            variable=self.activate_mode,
            value="online_code",
            font=self.config.FONT_SMALL,
            command=self._on_mode_change,
        ).pack(side="left", padx=10)

        # 输入区域（动态切换）
        self.input_label = ctk.CTkLabel(self.root, text="授权密钥", font=self.config.FONT_MAIN)
        self.input_label.pack(pady=5)

        self.input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.input_frame.pack(pady=2)

        # 授权密钥输入
        self.key_frame = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        self.key_entry = ctk.CTkEntry(
            self.key_frame,
            width=400,
            placeholder_text="粘贴生成的授权密钥",
            font=self.config.FONT_SMALL,
        )
        self.key_entry.pack()
        self.key_frame.pack()

        # 在线激活码输入
        self.online_frame = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        self.server_url_label = ctk.CTkLabel(
            self.online_frame, text="Server URL", font=self.config.FONT_SMALL
        )
        self.server_url_entry = ctk.CTkEntry(
            self.online_frame,
            width=400,
            placeholder_text="http://10.127.176.226:18080",
            font=self.config.FONT_SMALL,
        )
        self.server_url_entry.insert(0, self.config.ACTIVATION_SERVER_URL)
        self.server_url_label.pack(pady=(0, 2))
        self.server_url_entry.pack(pady=(0, 8))
        self.online_entry = ctk.CTkEntry(
            self.online_frame,
            width=400,
            placeholder_text="请输入16位在线激活码",
            font=self.config.FONT_SMALL,
        )
        self.online_entry.pack()
        self.online_frame.pack_forget()

        # 状态提示
        self.status_label = ctk.CTkLabel(
            self.root, text="", text_color="red", font=self.config.FONT_SMALL
        )
        self.status_label.pack(pady=5)

        # 激活按钮
        self.activate_button = ctk.CTkButton(
            self.root,
            text="激活软件",
            command=self._on_activate,
            fg_color=self.config.BTN_ACTIVE_COLOR,
            width=200,
            font=self.config.FONT_MAIN,
        )
        self.activate_button.pack(pady=15)

        self.progress_label = ctk.CTkLabel(self.root, text="", font=self.config.FONT_SMALL)
        self.progress_label.pack()

    def _on_mode_change(self):
        if self.activate_mode.get() == "license_key":
            self.input_label.configure(text="授权密钥")
            self.online_frame.pack_forget()
            self.key_frame.pack()
        else:
            self.input_label.configure(text="在线激活码")
            self.key_frame.pack_forget()
            self.online_frame.pack()

    def _on_activate_license_key(self):
        key = self.key_entry.get().strip()
        if not key:
            messagebox.showwarning("提示", "请输入密钥")
            return
        if not self.auth_manager.save_license(key):
            messagebox.showerror("失败", "密钥格式错误")
            self.status_label.configure(text="密钥无效", text_color="red")
            return
        ok, msg = self.auth_manager.check_auth()
        if not ok:
            messagebox.showerror("激活失败", msg)
            self.status_label.configure(text=msg, text_color="red")
            if self.auth_manager.license_path.exists():
                self.auth_manager.license_path.unlink()
            return
        self._launch_main()

    def _on_activate_online(self):
        code = self.online_entry.get().strip()
        if not code:
            messagebox.showwarning("提示", "请输入在线激活码")
            return
        if len(code) < 8:
            messagebox.showwarning("提示", "激活码格式不正确")
            return
        self.progress_label.configure(text="正在连接激活服务器...", text_color="#2563eb")
        self.activate_button.configure(state=ctk.DISABLED)
        server_url = self.server_url_entry.get().strip() or self.config.ACTIVATION_SERVER_URL

        def work():
            ok, msg = self.auth_manager.online_activate(code, server_url)
            self.root.after(0, lambda: self._finish_online_activation(ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _finish_online_activation(self, ok: bool, msg: str):
        self.activate_button.configure(state=ctk.NORMAL)
        if not ok:
            messagebox.showerror("激活失败", msg)
            if self.auth_manager.license_path.exists():
                self.auth_manager.license_path.unlink()
            self.status_label.configure(text=msg, text_color="red")
            self.progress_label.configure(text="")
            return
        self.progress_label.configure(text="")
        self._launch_main()

    def _on_activate(self):
        if self.activate_mode.get() == "license_key":
            self._on_activate_license_key()
        else:
            self._on_activate_online()

    def _launch_main(self):
        self.root.withdraw()
        self.root.destroy()
        self._on_activated()

    def run(self):
        self.root.mainloop()
        sys.exit()
