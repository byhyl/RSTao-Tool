# ui/theme.py
import customtkinter as ctk

FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_NORMAL = ("Microsoft YaHei UI", 11)
FONT_SMALL = ("Microsoft YaHei UI", 9)

THEME_DARK = {
    "bg": "#1e1f22", "panel": "#2b2d31", "card": "#313338",
    "menubar": "#252629", "statusbar": "#1a1b1e",
    "accent": "#00b4ff", "success": "#00d26a", "warning": "#ffb300",
    "danger": "#ff4d4f", "text_primary": "#e0e0e0",
    "text_secondary": "#b9bbbe", "border": "#3d4045",
    "hover": "#3a3c42", "dropdown": "#2b2d31",
}

THEME_LIGHT = {
    "bg": "#f0f0f5", "panel": "#e8e8ed", "card": "#ffffff",
    "menubar": "#dfdfe5", "statusbar": "#d8d8df",
    "accent": "#0078d4", "success": "#107c10", "warning": "#d83b01",
    "danger": "#e81123", "text_primary": "#1a1a1a",
    "text_secondary": "#555555", "border": "#c0c0c8",
    "hover": "#d5d5dc", "dropdown": "#ffffff",
}

_current_mode = "dark"
THEME = dict(THEME_DARK)

def apply_theme(mode):
    global _current_mode, THEME
    _current_mode = mode
    if mode == "dark":
        THEME.update(THEME_DARK)
        ctk.set_appearance_mode("Dark")
    else:
        THEME.update(THEME_LIGHT)
        ctk.set_appearance_mode("Light")

def get_current_mode():
    return _current_mode

CARD_STYLE = {
    "corner_radius": 8, "border_width": 1,
    "border_color": THEME["border"], "fg_color": THEME["card"],
}

PANEL_STYLE = {
    "corner_radius": 8, "border_width": 0, "fg_color": THEME["panel"],
}

class CollapsibleCard(ctk.CTkFrame):
    def __init__(self, parent, title):
        super().__init__(parent, **CARD_STYLE)
        self.is_expanded = True
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=10, pady=8)
        self.title_label = ctk.CTkLabel(self.header, text=title, font=FONT_SUBTITLE)
        self.title_label.pack(side="left")
        self.toggle_btn = ctk.CTkButton(
            self.header, text="▲", width=20, height=20,
            command=self.toggle, fg_color="transparent", hover_color=THEME["border"],
        )
        self.toggle_btn.pack(side="right")
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="x", padx=10, pady=(0, 10))

    def toggle(self):
        if self.is_expanded:
            self.content.pack_forget()
            self.toggle_btn.configure(text="▼")
        else:
            self.content.pack(fill="x", padx=10, pady=(0, 10))
            self.toggle_btn.configure(text="▲")
        self.is_expanded = not self.is_expanded

def init_theme():
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
