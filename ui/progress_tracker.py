"""统一进度反馈工具"""

from typing import Optional

import customtkinter as ctk


class ProgressTracker:
    """进度追踪器，统一更新进度条 + 状态文本"""

    def __init__(
        self,
        progress_bar: Optional[ctk.CTkProgressBar] = None,
        status_label: Optional[ctk.CTkLabel] = None,
        status_var: Optional[ctk.StringVar] = None,
    ):
        self._bar = progress_bar
        self._label = status_label
        self._var = status_var

    def start(self, total: int, message: str = "Processing..."):
        if self._bar:
            self._bar.set(0)
        self._update_text(message)

    def update(self, current: int, total: int, message: str = ""):
        if self._bar and total > 0:
            self._bar.set(current / total)
        if message:
            self._update_text(message)

    def finish(self, message: str = "Done"):
        if self._bar:
            self._bar.set(1.0)
        self._update_text(message)

    def error(self, message: str = "Failed"):
        self._update_text(message)

    def _update_text(self, text: str):
        if self._var:
            self._var.set(text)
        elif self._label:
            self._label.configure(text=text)
