"""在线激活码管理标签页"""

from tkinter import messagebox

import customtkinter as ctk
import pyperclip
from tkcalendar import DateEntry


class OnlineCodeTab:
    """Tab 2: 在线激活码管理"""

    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.config = app.config

    def build(self):
        tab = self.parent
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=0, minsize=380)
        tab.grid_columnconfigure(1, weight=1)

        # === 左侧：操作面板 ===
        left = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # 生成激活码卡片
        card = ctk.CTkFrame(left, corner_radius=10)
        card.pack(fill="x", pady=5)
        ctk.CTkLabel(card, text="生成激活码", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row1, text="类型", font=self.config.FONT_SMALL, width=80).pack(side="left")
        self._online_type = ctk.CTkOptionMenu(
            row1,
            values=["permanent", "days", "date"],
            command=self._on_online_type_change,
            font=self.config.FONT_SMALL,
            width=140,
        )
        self._online_type.pack(side="left")
        self._online_type.set("permanent")

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row2, text="可激活次数", font=self.config.FONT_SMALL, width=80).pack(
            side="left"
        )
        self._online_max = ctk.CTkEntry(
            row2, width=80, placeholder_text="1", font=self.config.FONT_SMALL
        )
        self._online_max.pack(side="left")
        self._online_max.insert(0, "1")

        self._online_param_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._online_param_frame.pack(fill="x", padx=15, pady=5)
        self._online_days_label = ctk.CTkLabel(
            self._online_param_frame, text="天数", font=self.config.FONT_SMALL
        )
        self._online_days_entry = ctk.CTkEntry(
            self._online_param_frame, width=80, placeholder_text="365", font=self.config.FONT_SMALL
        )
        self._online_date_label = ctk.CTkLabel(
            self._online_param_frame, text="截止日期", font=self.config.FONT_SMALL
        )
        self._online_date_picker = DateEntry(
            self._online_param_frame,
            width=16,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd",
            font=("Arial", 10),
            locale="zh_CN",
        )

        row4 = ctk.CTkFrame(card, fg_color="transparent")
        row4.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row4, text="备注", font=self.config.FONT_SMALL, width=80).pack(side="left")
        self._online_notes = ctk.CTkEntry(
            row4, placeholder_text="客户名称/用途", font=self.config.FONT_SMALL
        )
        self._online_notes.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            card,
            text="生成激活码",
            command=self._generate_online_code,
            fg_color=self.config.BTN_PRIMARY,
            hover_color=self.config.BTN_PRIMARY_HOVER,
            font=self.config.FONT_MAIN,
            height=36,
        ).pack(fill="x", padx=15, pady=10)

        result_card = ctk.CTkFrame(left, corner_radius=10)
        result_card.pack(fill="x", pady=5)
        ctk.CTkLabel(result_card, text="最近生成", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )
        self._online_result = ctk.CTkTextbox(
            result_card, height=100, wrap="word", font=self.config.FONT_MONO
        )
        self._online_result.pack(fill="x", padx=15, pady=(5, 5))
        ctk.CTkButton(
            result_card,
            text="复制激活码",
            command=self._copy_online_code,
            fg_color=self.config.BTN_SUCCESS,
            hover_color=self.config.BTN_SUCCESS_HOVER,
            font=self.config.FONT_SMALL,
            height=30,
        ).pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            left,
            text="刷新列表",
            command=self._refresh_online_data,
            fg_color="transparent",
            hover_color="#3d4045",
            font=self.config.FONT_SMALL,
            border_width=1,
            border_color="#3d4045",
        ).pack(fill="x", pady=5)

        # 黑名单管理
        bl_card = ctk.CTkFrame(left, corner_radius=10)
        bl_card.pack(fill="x", pady=5)
        ctk.CTkLabel(bl_card, text="黑名单管理", font=self.config.FONT_SUBTITLE).pack(
            anchor="w", padx=15, pady=(10, 0)
        )
        bl_row = ctk.CTkFrame(bl_card, fg_color="transparent")
        bl_row.pack(fill="x", padx=15, pady=5)
        self._bl_entry = ctk.CTkEntry(
            bl_row, placeholder_text="设备指纹或激活码", font=self.config.FONT_SMALL
        )
        self._bl_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(
            bl_row,
            text="加入黑名单",
            command=lambda: self._blacklist("add"),
            fg_color=self.config.BTN_DANGER,
            hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_SMALL,
            width=90,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bl_row,
            text="移除",
            command=lambda: self._blacklist("remove"),
            fg_color=self.config.BTN_WARNING,
            hover_color=self.config.BTN_WARNING_HOVER,
            font=self.config.FONT_SMALL,
            width=60,
        ).pack(side="left", padx=2)

        # 作废按钮
        ctk.CTkButton(
            left,
            text="作废选中激活码",
            command=self._revoke_code,
            fg_color=self.config.BTN_DANGER,
            hover_color=self.config.BTN_DANGER_HOVER,
            font=self.config.FONT_SMALL,
            height=32,
        ).pack(fill="x", pady=5)

        # === 右侧：数据展示 ===
        right = ctk.CTkTabview(tab, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        r1 = right.add("激活码列表")
        r2 = right.add("激活记录")
        r3 = right.add("黑名单")

        self._code_text = ctk.CTkTextbox(r1, wrap="none", font=self.config.FONT_MONO)
        self._code_text.pack(fill="both", expand=True, padx=5, pady=5)

        self._record_text = ctk.CTkTextbox(r2, wrap="none", font=self.config.FONT_MONO)
        self._record_text.pack(fill="both", expand=True, padx=5, pady=5)

        self._blacklist_text = ctk.CTkTextbox(r3, wrap="none", font=self.config.FONT_MONO)
        self._blacklist_text.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_online_type_change(self, choice):
        for w in self._online_param_frame.winfo_children():
            w.pack_forget()
        if choice == "days":
            self._online_days_label.pack(side="left", padx=5)
            self._online_days_entry.pack(side="left", padx=5)
        elif choice == "date":
            self._online_date_label.pack(side="left", padx=5)
            self._online_date_picker.pack(side="left", padx=5)

    def _generate_online_code(self):
        license_type = self._online_type.get()
        try:
            max_act = int(self._online_max.get().strip() or "1")
        except ValueError:
            messagebox.showerror("错误", "激活次数必须为数字")
            return
        notes = self._online_notes.get().strip()
        body = {"license_type": license_type, "max_activations": max_act, "notes": notes}
        if license_type == "days":
            try:
                body["expire_days"] = int(self._online_days_entry.get().strip() or "365")
            except ValueError:
                messagebox.showerror("错误", "天数必须为数字")
                return
        elif license_type == "date":
            body["expire_date"] = self._online_date_picker.get_date().strftime("%Y-%m-%d")
        result = self.app._api_call("POST", "/api/admin/generate", body)
        if result.get("success"):
            code = result["code"]
            self._online_result.delete(1.0, "end")
            self._online_result.insert("end", f"激活码: {code}\n")
            self._online_result.insert(
                "end", f"类型: {body['license_type']} | 最大次数: {body['max_activations']}\n"
            )
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
        for line in text.split("\n"):
            if line.startswith("激活码:"):
                code = line.split(":", 1)[1].strip()
                pyperclip.copy(code)
                messagebox.showinfo("成功", f"已复制: {code}")
                return
        messagebox.showwarning("提示", "未找到激活码")

    def _revoke_code(self):
        dialog = ctk.CTkInputDialog(
            text="输入要作废的激活码：", title="作废激活码", font=self.config.FONT_MAIN
        )
        code = dialog.get_input()
        if not code:
            return
        result = self.app._api_call("POST", "/api/admin/revoke", {"code": code.strip()})
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
        result = self.app._api_call(
            "POST",
            "/api/admin/blacklist",
            {"action": action, "identifier": identifier, "reason": "管理员操作"},
        )
        if result.get("success"):
            messagebox.showinfo("成功", result["message"])
            self._refresh_online_data()
        else:
            messagebox.showerror("失败", result.get("message", "操作失败"))

    def _refresh_online_data(self):
        codes = self.app._api_call("GET", "/api/admin/codes")
        self._code_text.delete(1.0, "end")
        if codes.get("codes"):
            header = f"{'激活码':<18} {'类型':<12} {'次数':<8} {'状态':<8} {'备注'}\n"
            self._code_text.insert("end", header)
            self._code_text.insert("end", "-" * 80 + "\n")
            for c in codes["codes"]:
                status = "有效" if c.get("is_active") else "已作废"
                color = "[有效]" if c.get("is_active") else "[作废]"
                notes = c.get("notes", "")[:20]
                self._code_text.insert(
                    "end",
                    f"{color} {c['code']:<16} {c['license_type']:<12} "
                    f"{c['current_activations']}/{c['max_activations']:<6} {status:<8} {notes}\n",
                )
        else:
            self._code_text.insert("end", f"加载失败: {codes.get('message', '未连接服务器')}")

        records = self.app._api_call("GET", "/api/admin/records")
        self._record_text.delete(1.0, "end")
        if records.get("records"):
            header = f"{'时间':<20} {'激活码':<18} {'设备指纹'}\n"
            self._record_text.insert("end", header)
            self._record_text.insert("end", "-" * 80 + "\n")
            for r in records["records"]:
                fp = r.get("device_fingerprint", "")[:30]
                self._record_text.insert(
                    "end", f"{r['activated_at']:<20} {r['activation_code']:<18} {fp}\n"
                )
        else:
            self._record_text.insert("end", f"加载失败: {records.get('message', '未连接服务器')}")

        bl = self.app._api_call("GET", "/api/admin/blacklist")
        self._blacklist_text.delete(1.0, "end")
        if bl.get("blacklist"):
            for b in bl["blacklist"]:
                self._blacklist_text.insert(
                    "end", f"[黑名单] {b['identifier']:<40} {b.get('reason','')}\n"
                )
        else:
            self._blacklist_text.insert("end", f"黑名单为空 ({bl.get('message','')})")
