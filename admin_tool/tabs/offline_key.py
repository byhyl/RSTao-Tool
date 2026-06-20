"""Offline signed license generation tab."""

from datetime import datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk
import pyperclip
from tkcalendar import DateEntry

from common.license_crypto import (
    create_license_payload,
    load_private_key_from_env,
    private_key_matches_public,
    sign_license_payload,
)
from common.logger import logger


class OfflineKeyTab:
    """Tab 1: offline signed license generation."""

    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.config = app.config
        self.license_type = "永久授权"
        self._machine_entry = None
        self._offline_param_frame = None
        self._offline_key_output = None
        self._day_label = None
        self._day_entry = None
        self._date_label = None
        self._date_picker = None

    def build(self):
        scroll = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=10)

        card1 = ctk.CTkFrame(scroll, corner_radius=10)
        card1.pack(fill="x", pady=5)
        ctk.CTkLabel(card1, text="用户机器码", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )
        self._machine_entry = ctk.CTkEntry(
            card1,
            height=36,
            placeholder_text="请输入用户提供的机器码（16位MD5）",
            font=self.config.FONT_MAIN,
        )
        self._machine_entry.pack(fill="x", padx=15, pady=(5, 10))

        card2 = ctk.CTkFrame(scroll, corner_radius=10)
        card2.pack(fill="x", pady=5)
        ctk.CTkLabel(card2, text="授权类型", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )
        type_row = ctk.CTkFrame(card2, fg_color="transparent")
        type_row.pack(fill="x", padx=15, pady=5)
        type_option = ctk.CTkOptionMenu(
            type_row,
            values=["永久授权", "按天数授权", "指定日期过期"],
            command=self._on_license_type_change,
            font=self.config.FONT_MAIN,
            width=160,
        )
        type_option.pack(side="left")
        type_option.set("永久授权")
        self._offline_param_frame = ctk.CTkFrame(card2, fg_color="transparent")
        self._offline_param_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._day_label = ctk.CTkLabel(
            self._offline_param_frame, text="授权天数", font=self.config.FONT_MAIN
        )
        self._day_entry = ctk.CTkEntry(
            self._offline_param_frame, width=120, placeholder_text=">=1", font=self.config.FONT_MAIN
        )
        self._date_label = ctk.CTkLabel(
            self._offline_param_frame, text="过期日期", font=self.config.FONT_MAIN
        )
        self._date_picker = DateEntry(
            self._offline_param_frame,
            width=18,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd",
            font=("Arial", 12),
            locale="zh_CN",
        )

        card3 = ctk.CTkFrame(scroll, corner_radius=10)
        card3.pack(fill="x", pady=5)
        ctk.CTkLabel(card3, text="生成的签名授权", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )
        self._offline_key_output = ctk.CTkTextbox(
            card3, height=70, wrap="word", font=self.config.FONT_MONO
        )
        self._offline_key_output.pack(fill="x", padx=15, pady=(5, 5))
        self._offline_key_output.configure(state="disabled")

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(
            btn_row,
            text="生成授权",
            command=self._generate_offline_key,
            fg_color=self.config.BTN_PRIMARY,
            hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN,
            width=130,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row,
            text="复制授权",
            command=self._copy_offline_key,
            fg_color=self.config.BTN_SUCCESS,
            hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_MAIN,
            width=130,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row,
            text="清空",
            command=lambda: [
                self._offline_key_output.configure(state="normal"),
                self._offline_key_output.delete(1.0, "end"),
                self._offline_key_output.configure(state="disabled"),
            ],
            fg_color="transparent",
            hover_color="#3d4045",
            font=self.config.FONT_MAIN,
            width=80,
            border_width=1,
            border_color="#3d4045",
        ).pack(side="left", padx=5)

    def _on_license_type_change(self, choice):
        self.license_type = choice
        for widget in self._offline_param_frame.winfo_children():
            widget.pack_forget()
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
        if machine.upper() == "UNKNOWN":
            messagebox.showerror("错误", "机器码读取失败，不能为 UNKNOWN 生成授权")
            return
        if machine != "UNKNOWN":
            if len(machine) != 16:
                if not messagebox.askyesno("警告", "机器码长度不是16位，是否继续生成？"):
                    return
            try:
                int(machine, 16)
            except ValueError:
                messagebox.showerror("错误", "机器码格式无效")
                return

        private_key = load_private_key_from_env()
        if not private_key:
            messagebox.showerror(
                "缺少授权私钥",
                "请通过 RSTAO_LICENSE_PRIVATE_KEY_FILE 指定私钥 PEM 文件，"
                "或通过 RSTAO_LICENSE_PRIVATE_KEY 传入私钥内容。",
            )
            return
        if not private_key_matches_public(private_key):
            messagebox.showerror(
                "私钥不匹配", "当前私钥与客户端内置公钥不匹配，生成的授权无法使用。"
            )
            return

        try:
            expire_dt = self._resolve_expire_date()
            payload = create_license_payload(
                machine_code=machine,
                expire_ts=expire_dt.timestamp(),
                license_type=self.license_type,
            )
            license_key = sign_license_payload(payload, private_key)
            self._offline_key_output.configure(state="normal")
            self._offline_key_output.delete(1.0, "end")
            self._offline_key_output.insert("end", license_key)
            self._offline_key_output.configure(state="disabled")
            logger.info(f"离线签名授权生成: {machine[:8]}... -> {expire_dt:%Y-%m-%d}")
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
        except Exception as e:
            messagebox.showerror("错误", f"生成失败: {e}")

    def _resolve_expire_date(self) -> datetime:
        if self.license_type == "永久授权":
            return datetime(2099, 12, 31)
        if self.license_type == "按天数授权":
            days = int(self._day_entry.get().strip() or "0")
            if days <= 0:
                raise ValueError("授权天数必须大于0")
            return datetime.now() + timedelta(days=days)

        date_str = self._date_picker.get_date().strftime("%Y-%m-%d")
        expire_dt = datetime.strptime(date_str, "%Y-%m-%d")
        if expire_dt < datetime.now():
            raise ValueError("过期日期不能早于当前日期")
        return expire_dt

    def _copy_offline_key(self):
        key = self._offline_key_output.get(1.0, "end-1c").strip()
        if not key:
            messagebox.showwarning("提示", "没有可复制的授权")
            return
        try:
            pyperclip.copy(key)
            messagebox.showinfo("成功", "授权已复制到剪贴板")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")
