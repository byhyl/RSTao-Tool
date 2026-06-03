import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Dict, Optional, Tuple

import customtkinter as ctk
import wmi

from common.crypto import aes_gcm_decrypt, aes_gcm_encrypt, generate_machine_code_hash
from common.logger import logger

# 本地模块导入
from ui import MainWindow


# ====================== 配置常量 ======================
@dataclass
class AuthConfig:
    LICENSE_FILE_NAME: str = ".license.dat"
    ACTIVATION_WINDOW_SIZE: str = "500x420"
    ACTIVATION_WINDOW_TITLE: str = "RSTao-Tool - 授权激活"
    FONT_MAIN: tuple = ("Microsoft YaHei", 14)
    FONT_SMALL: tuple = ("Microsoft YaHei", 12)
    BTN_ACTIVE_COLOR: str = "#2563eb"
    # 在线激活服务器地址（可配置）
    ACTIVATION_SERVER_URL: str = "http://127.0.0.1:18080"
    ACTIVATION_TIMEOUT: int = 10  # 秒


# ====================== 授权核心类 ======================
class AuthManager:
    """授权管理核心类（封装所有授权逻辑）"""
    _ANTI_TAMPER_FILE = Path(__file__).parent / ".rstao_ts"
    def __init__(self, config: AuthConfig = AuthConfig()):
        self.config = config
        self.license_path = Path(sys.argv[0]).parent / self.config.LICENSE_FILE_NAME
        self._machine_code: Optional[str] = None

    # --- 加密/解密委托给 common.crypto (AES-256-GCM) ---
    def encrypt_data(self, text: str) -> Optional[str]:
        return aes_gcm_encrypt(text)

    def decrypt_data(self, text: str) -> Optional[str]:
        return aes_gcm_decrypt(text)

    def get_machine_code(self) -> str:
        """获取机器码（增强容错）"""
        if self._machine_code:
            return self._machine_code
        try:
            c = wmi.WMI()
            # 获取CPU ID
            cpu_info = c.Win32_Processor()[0]
            cpu_id = cpu_info.ProcessorId.strip() if hasattr(cpu_info, "ProcessorId") else ""

            # 获取硬盘序列号
            try:
                disk_info = c.Win32_PhysicalMedia()[0]
                disk_sn = (
                    disk_info.SerialNumber.strip() if hasattr(disk_info, "SerialNumber") else ""
                )
            except Exception:
                disk_sn = ""

            # 生成MD5机器码
            machine_str = f"{cpu_id}_{disk_sn}"
            if not machine_str.strip("_"):
                raise ValueError("无法获取硬件信息")

            raw_code = hashlib.md5(machine_str.encode()).hexdigest()[:16]
            self._machine_code = raw_code
            return raw_code
        except ImportError:
            logger.error("获取机器码失败：缺少wmi模块")
        except IndexError:
            logger.error("获取机器码失败：硬件信息读取异常")
        except Exception as e:
            logger.error(f"获取机器码失败：{str(e)}", exc_info=True)

        # 降级方案：返回固定值
        self._machine_code = "UNKNOWN"
        return "UNKNOWN"

    def get_machine_code_hashed(self) -> str:
        """获取哈希后的机器码（不暴露原始硬件信息）"""
        raw = self.get_machine_code()
        return generate_machine_code_hash(raw)

    def get_device_fingerprint(self) -> str:
        """获取设备唯一指纹，用于服务端绑定"""
        try:
            return str(uuid.getnode()) + "_" + self.get_machine_code()
        except Exception:
            return "UNKNOWN_" + str(uuid.getnode())

    def read_auth(self) -> Optional[str]:
        """读取授权文件（增强容错）"""
        if not self.license_path.exists():
            logger.info("授权文件不存在")
            return None

        try:
            with open(self.license_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                logger.warning("授权文件为空")
                return None
            return content
        except PermissionError:
            logger.error("读取授权文件失败：权限不足")
        except Exception as e:
            logger.error(f"读取授权文件失败：{str(e)}", exc_info=True)
        return None

    def write_auth(self, data: str) -> bool:
        """写入授权文件（增强容错）"""
        try:
            self.license_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.license_path, "w", encoding="utf-8") as f:
                f.write(data)
            # 隐藏文件
            try:
                import os

                os.system(f'attrib +h "{self.license_path}"')
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"写入授权文件失败：{str(e)}", exc_info=True)
            return False

    def check_auth(self) -> Tuple[bool, str]:
        """校验授权（增强返回格式）"""
        # 读取授权文件
        encrypted = self.read_auth()
        if not encrypted:
            return False, "未检测到授权文件，请激活软件"

        # 获取机器码
        try:
            machine_code = self.get_machine_code()
        except (ImportError, IndexError, Exception):
            logger.warning("无法获取机器码，跳过硬件验证")
            return True, "跳过硬件验证"

        # 解密授权文件
        decrypted = self.decrypt_data(encrypted)
        if decrypted is None:
            logger.warning("授权解密失败，文件可能被篡改")
            return False, "授权文件无效或被篡改"

        # 验证机器码
        if machine_code not in decrypted and machine_code != "UNKNOWN":
            logger.warning(f"机器码不匹配: {machine_code}")
            return False, "机器码不匹配"

        # 验证过期时间
        if self.is_expired(decrypted.split("|")[1] if "|" in decrypted else "0"):
            return False, "授权已过期"

        # ??????????????
        tamper_msg = self._check_clock_tamper()
        if tamper_msg:
            return False, tamper_msg

        # ????????
        self._save_last_valid_time()

        return True, "????"


    def is_expired(self, expire_str: str) -> bool:
        """验证是否过期"""
        try:
            expire_ts = float(expire_str)
            current_ts = time.time()
            return current_ts > expire_ts
        except ValueError:
            return True

    def _check_clock_tamper(self) -> str:
        """???????????????????????"""
        try:
            now = time.time()
            if self._ANTI_TAMPER_FILE.exists():
                saved = float(self._ANTI_TAMPER_FILE.read_text().strip())
                if now < saved - 86400:
                    logger.warning(f"??????: now={now} saved={saved}")
                    return "?????????????????"
        except Exception:
            pass
        return ""

    def _save_last_valid_time(self):
        """????????????"""
        try:
            self._ANTI_TAMPER_FILE.write_text(str(time.time()))
            try:
                import os; os.system(chr(97)+chr(116)+chr(116)+chr(114)+chr(105)+chr(98)+chr(32)+chr(43)+chr(104)+chr(32)+chr(34)+str(self._ANTI_TAMPER_FILE)+chr(34))
            except Exception:
                pass
        except Exception:
            pass


    def save_license(self, key: str) -> bool:
        """保存授权密钥"""
        machine_code = self.get_machine_code()
        expire_ts = self.decrypt_data(key)
        if expire_ts is None:
            return False

        # 验证机器码是否匹配
        if machine_code not in expire_ts and machine_code != "UNKNOWN":
            logger.warning("机器码不匹配")
            return False

        encrypted = self.encrypt_data(expire_ts)
        if not encrypted:
            return False

        return self.write_auth(encrypted)

    def online_activate(self, activation_code: str, server_url: str = None) -> Tuple[bool, str]:
        """在线激活：向服务端发送激活码+设备指纹进行验证"""
        try:
            payload = {
                "activation_code": activation_code,
                "device_fingerprint": self.get_device_fingerprint(),
                "machine_code": self.get_machine_code_hashed(),
                "timestamp": datetime.now().isoformat(),
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{server_url or self.config.ACTIVATION_SERVER_URL}/api/activate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.config.ACTIVATION_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            if result.get("success"):
                license_key = result.get("license_key")
                if license_key and self.save_license(license_key):
                    logger.info("??????")
                    return True, "??????"
                return False, "License save failed - please restart admin tool"
            else:
                return False, result.get("message", "????")

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            logger.error(f"激活服务器返回错误: {e.code} - {error_body}")
            return False, f"服务器拒绝 ({e.code})"
        except urllib.error.URLError as e:
            logger.error(f"无法连接激活服务器: {e.reason}")
            return False, "无法连接激活服务器，请检查网络"
        except Exception as e:
            logger.error(f"在线激活异常: {e}", exc_info=True)
            return False, f"激活异常: {str(e)}"


# ====================== 激活界面 ======================
class ActivationUI:
    """激活界面（封装为类）"""

    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.config = auth_manager.config
        self.root = ctk.CTk()
        self._init_window()
        self._create_ui()

    def _init_window(self):
        """初始化激活窗口"""
        self.root.title(self.config.ACTIVATION_WINDOW_TITLE)
        self.root.geometry(self.config.ACTIVATION_WINDOW_SIZE)
        self.root.resizable(False, False)

        # 居中显示
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.root.winfo_width()) // 2
        y = (sh - self.root.winfo_height()) // 2
        self.root.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """创建激活界面UI"""
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

        # --- 激活方式选择 ---
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

        # --- 输入区域（动态切换）---
        self.input_label = ctk.CTkLabel(self.root, text="授权密钥", font=self.config.FONT_MAIN)
        self.input_label.pack(pady=5)

        self.input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.input_frame.pack(pady=2)

        # 授权密钥输入（默认显示）
        self.key_frame = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        self.key_entry = ctk.CTkEntry(
            self.key_frame,
            width=400,
            placeholder_text="粘贴生成的授权密钥",
            font=self.config.FONT_SMALL,
        )
        self.key_entry.pack()
        self.key_frame.pack()

        # 在线激活码输入（默认隐藏）
        self.online_frame = ctk.CTkFrame(self.input_frame, fg_color="transparent")

        # server address input
        self.server_url_label = ctk.CTkLabel(self.online_frame, text="Server URL", font=self.config.FONT_SMALL)
        self.server_url_entry = ctk.CTkEntry(
            self.online_frame,
            width=400,
            placeholder_text="http://10.127.176.226:18080",
            font=self.config.FONT_SMALL,
        )
        self.server_url_entry.insert(0, self.config.ACTIVATION_SERVER_URL)
        self.server_url_label.pack(pady=(0,2))
        self.server_url_entry.pack(pady=(0,8))
        self.online_entry = ctk.CTkEntry(
            self.online_frame,
            width=400,
            placeholder_text="请输入16位在线激活码",
            font=self.config.FONT_SMALL,
        )
        self.online_entry.pack()
        # 默认隐藏在线激活码输入框
        self.online_frame.pack_forget()

        # 状态提示
        self.status_label = ctk.CTkLabel(
            self.root, text="", text_color="red", font=self.config.FONT_SMALL
        )
        self.status_label.pack(pady=5)

        # 激活按钮
        ctk.CTkButton(
            self.root,
            text="激活软件",
            command=self._on_activate,
            fg_color=self.config.BTN_ACTIVE_COLOR,
            width=200,
            font=self.config.FONT_MAIN,
        ).pack(pady=15)

        # 进度提示
        self.progress_label = ctk.CTkLabel(self.root, text="", font=self.config.FONT_SMALL)
        self.progress_label.pack()

    def _on_mode_change(self):
        """切换激活方式"""
        if self.activate_mode.get() == "license_key":
            self.input_label.configure(text="授权密钥")
            self.online_frame.pack_forget()
            self.key_frame.pack()
        else:
            self.input_label.configure(text="在线激活码")
            self.key_frame.pack_forget()
            self.online_frame.pack()

    def _on_activate_license_key(self):
        """处理离线密钥激活"""
        key = self.key_entry.get().strip()
        if not key:
            messagebox.showwarning("提示", "请输入密钥")
            return

        # 保存授权密钥
        if not self.auth_manager.save_license(key):
            messagebox.showerror("失败", "密钥格式错误")
            self.status_label.configure(text="密钥无效", text_color="red")
            return

        # 校验授权
        ok, msg = self.auth_manager.check_auth()
        if not ok:
            messagebox.showerror("激活失败", msg)
            self.status_label.configure(text=msg, text_color="red")
            # 清理无效授权文件
            if self.auth_manager.license_path.exists():
                self.auth_manager.license_path.unlink()
            return

        # 激活成功
        self.root.withdraw()
        self.root.destroy()
        start_main()

    def _on_activate_online(self):
        """处理在线激活"""
        code = self.online_entry.get().strip()
        if not code:
            messagebox.showwarning("提示", "请输入在线激活码")
            return

        if len(code) < 8:
            messagebox.showwarning("提示", "激活码格式不正确")
            return

        self.progress_label.configure(text="正在连接激活服务器...", text_color="#2563eb")
        self.root.update()

        server_url = self.server_url_entry.get().strip() or self.config.ACTIVATION_SERVER_URL
        ok, msg = self.auth_manager.online_activate(code, server_url)
        if not ok:
            messagebox.showerror("激活失败", msg)
            self.status_label.configure(text=msg, text_color="red")
            self.progress_label.configure(text="")
            return

        self.progress_label.configure(text="")
        self.root.withdraw()
        self.root.destroy()
        start_main()

    def _on_activate(self):
        """统一激活入口"""
        if self.activate_mode.get() == "license_key":
            self._on_activate_license_key()
        else:
            self._on_activate_online()

    def run(self):
        """运行激活界面"""
        self.root.mainloop()
        sys.exit()


# ====================== 启动函数 ======================
def start_main():
    """启动主程序"""
    try:
        app = MainWindow()
        app.mainloop()
    except Exception as e:
        logger.critical("主程序启动失败", exc_info=True)
        messagebox.showerror("致命错误", f"主程序启动失败：{str(e)}")
        sys.exit(1)


def main():
    """程序入口"""
    try:
        # 初始化授权管理器
        auth_manager = AuthManager()

        # 校验授权
        ok, msg = auth_manager.check_auth()

        # 启动主程序或激活界面
        if ok:
            logger.info("授权校验通过，启动主程序")
            start_main()
        else:
            logger.info(f"授权校验失败：{msg}，启动激活界面")
            activation_ui = ActivationUI(auth_manager)
            activation_ui.run()
    except Exception as e:
        logger.critical("程序初始化失败", exc_info=True)
        messagebox.showerror("致命错误", f"程序初始化失败：{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()


