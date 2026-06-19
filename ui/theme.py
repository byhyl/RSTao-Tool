# ui/theme.py — RSTao-Tool 统一主题系统
import customtkinter as ctk

# ====================== 字体系统 ======================
FONT_HERO = ("Microsoft YaHei UI", 28, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 18, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_NORMAL = ("Microsoft YaHei UI", 12)
FONT_SMALL = ("Microsoft YaHei UI", 11)
FONT_MONO = ("Consolas", 11)

# ====================== 深色主题 ======================
THEME_DARK = {
    "bg": "#0f1117",
    "panel": "#161822",
    "card": "#1c1f2e",
    "menubar": "#12141c",
    "statusbar": "#0d0f14",
    "accent": "#6366f1",
    "accent_hover": "#5558e6",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "text_primary": "#e2e4e9",
    "text_secondary": "#8b8fa3",
    "text_muted": "#5b5f72",
    "border": "#252836",
    "hover": "#222538",
    "dropdown": "#1a1d2d",
    "divider": "#1f2233",
    "gradient_start": "#6366f1",
    "gradient_end": "#8b5cf6",
}

# ====================== 浅色主题 ======================
THEME_LIGHT = {
    "bg": "#f8f9fc",
    "panel": "#ffffff",
    "card": "#ffffff",
    "menubar": "#f1f3f8",
    "statusbar": "#eaecf2",
    "accent": "#4f46e5",
    "accent_hover": "#4338ca",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "text_primary": "#111827",
    "text_secondary": "#6b7280",
    "text_muted": "#9ca3af",
    "border": "#e2e4ea",
    "hover": "#eef0f6",
    "dropdown": "#ffffff",
    "divider": "#e8eaf0",
    "gradient_start": "#4f46e5",
    "gradient_end": "#7c3aed",
}

# ====================== 全局状态 ======================
_current_mode = "dark"
THEME = dict(THEME_DARK)


def apply_theme(mode: str):
    global _current_mode, THEME
    _current_mode = mode
    if mode == "dark":
        THEME.update(THEME_DARK)
        ctk.set_appearance_mode("Dark")
    else:
        THEME.update(THEME_LIGHT)
        ctk.set_appearance_mode("Light")
    CARD_STYLE["border_color"] = THEME["border"]
    CARD_STYLE["fg_color"] = THEME["card"]
    PANEL_STYLE["fg_color"] = THEME["panel"]
    SECTION_STYLE["border_color"] = THEME["border"]
    SECTION_STYLE["fg_color"] = THEME["card"]


def get_current_mode() -> str:
    return _current_mode


# ====================== 组件样式 ======================
CARD_STYLE = {
    "corner_radius": 10,
    "border_width": 1,
    "border_color": THEME["border"],
    "fg_color": THEME["card"],
}

PANEL_STYLE = {
    "corner_radius": 10,
    "border_width": 0,
    "fg_color": THEME["panel"],
}

SECTION_STYLE = {
    "corner_radius": 8,
    "border_width": 1,
    "border_color": THEME["border"],
    "fg_color": THEME["card"],
}


# ====================== CollapsibleCard ======================
class CollapsibleCard(ctk.CTkFrame):
    def __init__(self, parent, title):
        super().__init__(parent, **CARD_STYLE)
        self.is_expanded = True
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=12, pady=8)
        self.title_label = ctk.CTkLabel(self.header, text=title, font=FONT_SUBTITLE)
        self.title_label.pack(side="left")
        self.toggle_btn = ctk.CTkButton(
            self.header,
            text="\u25b2",
            width=24,
            height=24,
            command=self.toggle,
            fg_color="transparent",
            hover_color=THEME["border"],
        )
        self.toggle_btn.pack(side="right")
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="x", padx=12, pady=(0, 10))

    def toggle(self):
        if self.is_expanded:
            self.content.pack_forget()
            self.toggle_btn.configure(text="\u25bc")
        else:
            self.content.pack(fill="x", padx=12, pady=(0, 10))
            self.toggle_btn.configure(text="\u25b2")
        self.is_expanded = not self.is_expanded


def init_theme():
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
