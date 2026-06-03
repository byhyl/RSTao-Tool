# ui/theme.py
import customtkinter as ctk

# ========== 字体配置（所有模块统一使用） ==========
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_NORMAL = ("Microsoft YaHei UI", 11)
FONT_SMALL = ("Microsoft YaHei UI", 9)

# ========== 颜色配置（ArcGIS Pro 深色风格） ==========
THEME = {
    "bg": "#1e1f22",               # 主背景色
    "panel": "#2b2d31",            # 面板背景色
    "card": "#313338",             # 卡片背景色
    "accent": "#00b4ff",           # 强调色（蓝色）
    "success": "#00d26a",          # 成功色
    "warning": "#ffb300",          # 警告色
    "danger": "#ff4d4f",           # 危险色
    "text_primary": "#ffffff",     # 主要文字色
    "text_secondary": "#b9bbbe",   # 次要文字色
    "border": "#3d4045",           # 边框色
}

# ========== 控件样式（所有模块统一使用） ==========
CARD_STYLE = {
    "corner_radius": 8,
    "border_width": 1,
    "border_color": THEME["border"],
    "fg_color": THEME["card"],
}

PANEL_STYLE = {
    "corner_radius": 8,
    "border_width": 0,
    "fg_color": THEME["panel"],
}

# ========== 通用可折叠卡片组件（修复版） ==========
class CollapsibleCard(ctk.CTkFrame):
    def __init__(self, parent, title):
        super().__init__(parent, **CARD_STYLE)
        self.is_expanded = True
        
        # 标题栏
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=10, pady=8)
        
        self.title_label = ctk.CTkLabel(self.header, text=title, font=FONT_SUBTITLE)
        self.title_label.pack(side="left")
        
        self.toggle_btn = ctk.CTkButton(
            self.header, text="▼", width=20, height=20,
            command=self.toggle, fg_color="transparent", hover_color=THEME["border"]
        )
        self.toggle_btn.pack(side="right")
        
        # 内容区（修复：确保内容区可见）
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="x", padx=10, pady=(0, 10))

    def toggle(self):
        if self.is_expanded:
            self.content.pack_forget()
            self.toggle_btn.configure(text="▶")
        else:
            self.content.pack(fill="x", padx=10, pady=(0, 10))
            self.toggle_btn.configure(text="▼")
        self.is_expanded = not self.is_expanded

# ========== 初始化全局主题 ==========
def init_theme():
    # 设置深色主题（所有版本都支持）
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")