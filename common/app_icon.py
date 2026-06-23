"""Shared application icon helpers."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

APP_ICON_RELATIVE_PATH = Path("assets") / "icon.ico"
logger = logging.getLogger("RSTao-Tool")


def _runtime_base_candidates() -> list[Path]:
    candidates: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    candidates.append(Path(__file__).resolve().parent.parent)
    return candidates


def resolve_app_icon_path() -> Path:
    """Return the bundled application icon path when available."""
    for base_path in _runtime_base_candidates():
        icon_path = base_path / APP_ICON_RELATIVE_PATH
        if icon_path.exists():
            return icon_path
    return _runtime_base_candidates()[-1] / APP_ICON_RELATIVE_PATH


def apply_app_icon(window) -> bool:
    """Apply the shared .ico to a Tk/CustomTkinter window."""
    icon_path = resolve_app_icon_path()
    if not icon_path.exists():
        logger.debug(f"应用图标不存在: {icon_path}")
        return False

    applied = False
    try:
        window.iconbitmap(str(icon_path))
        applied = True
    except Exception as exc:
        logger.debug(f"iconbitmap 设置失败: {exc}")

    try:
        from PIL import Image, ImageTk

        image = Image.open(icon_path)
        tk_image = ImageTk.PhotoImage(image)
        window.wm_iconphoto(True, tk_image)
        refs = getattr(window, "_app_icon_refs", [])
        refs.append(tk_image)
        window._app_icon_refs = refs
        applied = True
    except Exception as exc:
        logger.debug(f"wm_iconphoto 设置失败: {exc}")

    if not applied:
        logger.warning(f"窗口图标设置失败: {icon_path}")
    return applied
