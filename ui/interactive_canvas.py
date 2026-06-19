"""可漫游放缩的 Matplotlib 画布 — 用于影像显示面板"""

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class InteractiveCanvas:
    """为 FigureCanvasTkAgg 添加鼠标滚轮缩放和拖拽平移

    用法:
        canvas = InteractiveCanvas.wrap(figure_canvas)
        # 之后鼠标滚轮缩放、左键拖拽平移即生效
    """

    def __init__(self, canvas: FigureCanvasTkAgg):
        self.canvas = canvas
        self._press_xy = None
        self._xlim = None
        self._ylim = None

        canvas.mpl_connect("button_press_event", self._on_press)  # 中键=平移
        canvas.mpl_connect("button_release_event", self._on_release)
        canvas.mpl_connect("motion_notify_event", self._on_motion)
        canvas.mpl_connect("scroll_event", self._on_scroll)

    def _on_press(self, event):
        if event.button == 2 and event.inaxes:
            self._press_xy = (event.xdata, event.ydata)
            ax = event.inaxes
            self._xlim = ax.get_xlim()
            self._ylim = ax.get_ylim()

    def _on_release(self, event):
        self._press_xy = None

    def _on_motion(self, event):
        if self._press_xy is None or event.inaxes is None:
            return
        ax = event.inaxes
        dx = self._press_xy[0] - event.xdata
        dy = self._press_xy[1] - event.ydata
        ax.set_xlim(self._xlim[0] + dx, self._xlim[1] + dx)
        ax.set_ylim(self._ylim[0] + dy, self._ylim[1] + dy)
        self.canvas.draw_idle()

    def _on_scroll(self, event):
        if event.inaxes is None:
            return
        ax = event.inaxes
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        scale = 0.85 if event.button == "up" else 1.0 / 0.85

        cx, cy = event.xdata, event.ydata
        if cx is None or cy is None:
            return

        new_x_half = (xlim[1] - xlim[0]) / 2 * scale
        new_y_half = (ylim[1] - ylim[0]) / 2 * scale
        ax.set_xlim(cx - new_x_half, cx + new_x_half)
        ax.set_ylim(cy - new_y_half, cy + new_y_half)
        self.canvas.draw_idle()

    @classmethod
    def wrap(cls, canvas: FigureCanvasTkAgg):
        """包装画布，启用交互"""
        return cls(canvas)

    @classmethod
    def wrap_all(cls, canvas_list: list):
        """批量包装"""
        return [cls(c) for c in canvas_list]
