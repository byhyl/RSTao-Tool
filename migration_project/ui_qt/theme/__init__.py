"""Theme helpers for the Qt preview UI."""

from __future__ import annotations

from pathlib import Path

DEFAULT_THEME = "light"
AVAILABLE_THEMES = ("light", "dark")


def load_stylesheet(name: str = DEFAULT_THEME) -> str:
    if name not in AVAILABLE_THEMES:
        name = DEFAULT_THEME
    qss_path = Path(__file__).with_name(f"{name}.qss")
    if not qss_path.exists():
        return ""
    return qss_path.read_text(encoding="utf-8")
