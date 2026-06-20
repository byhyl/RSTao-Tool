"""GIS 栅格影像查看器 - 像素级漫游 + 叠加层 + 大文件优化"""

import math
import os
from tkinter import filedialog

import numpy as np
from PIL import Image, ImageTk

Image.MAX_IMAGE_PIXELS = None  # 允许超大影像
import customtkinter as ctk

from core.spatial_reference import normalize_geo_transform

from .theme import FONT_SMALL, THEME
from .ui_helpers import notify


class RasterViewer(ctk.CTkFrame):
    """可漫游缩放的栅格影像查看器，支持点/框/线/多边形叠加层。

    操作: 鼠标中键拖拽=平移 | 滚轮=缩放 | 悬停显示像素和地理坐标
    """

    def __init__(
        self,
        parent,
        on_coord_change=None,
        on_mouse_down=None,
        on_mouse_up=None,
        on_mouse_move=None,
        on_dblclick=None,
    ):
        super().__init__(parent, fg_color=THEME["card"])
        self._on_coord_change = on_coord_change
        self._on_mouse_down = on_mouse_down
        self._on_mouse_up = on_mouse_up
        self._on_mouse_move = on_mouse_move
        self._on_dblclick = on_dblclick
        self._pil_image = None
        self._img_width = 0
        self._img_height = 0
        self._overview_scale = 1.0
        self._geo_transform = (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
        self._has_geo_transform = False
        self._overlays = []
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._zoom = 1.0
        self._min_zoom = 0.01
        self._max_zoom = 50.0
        self._drag_start = None
        self._tk_img = None

        self._toolbar = ctk.CTkFrame(self, height=30, fg_color=THEME["statusbar"], corner_radius=0)
        self._toolbar.pack(fill="x", side="top")
        self._toolbar.pack_propagate(False)
        self._build_toolbar()

        self._canvas = ctk.CTkCanvas(
            self, bg=THEME["card"], highlightthickness=0, cursor="crosshair"
        )
        self._canvas.pack(fill="both", expand=True)
        # 中键拖拽=平移，滚轮=缩放
        self._canvas.bind("<Button-2>", self._on_press)
        self._canvas.bind("<B2-Motion>", self._on_drag)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Button-1>", self._on_left_press)
        self._canvas.bind("<B1-Motion>", self._on_left_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self._canvas.bind("<Double-Button-1>", self._on_left_dblclick)
        self._canvas.bind("<Button-3>", self._on_right_click)

    def _build_toolbar(self):
        def small_btn(text, command, width=34):
            btn = ctk.CTkButton(
                self._toolbar,
                text=text,
                width=width,
                height=24,
                fg_color="transparent",
                hover_color=THEME["hover"],
                text_color=THEME["text_secondary"],
                font=("Microsoft YaHei UI", 10),
                corner_radius=4,
                command=command,
            )
            btn.pack(side="left", padx=(4, 0), pady=3)
            return btn

        small_btn("适应", self.fit_to_view, width=46)
        small_btn("1:1", self.zoom_actual, width=34)
        small_btn("-", lambda: self.zoom_by(1 / 1.25), width=28)
        small_btn("+", lambda: self.zoom_by(1.25), width=28)
        small_btn("截图", self.export_screenshot, width=46)
        self._zoom_label = ctk.CTkLabel(
            self._toolbar,
            text="100%",
            width=58,
            anchor="e",
            font=FONT_SMALL,
            text_color=THEME["text_muted"],
        )
        self._zoom_label.pack(side="right", padx=8)

    # ==================== 加载 ====================
    def load(self, path="", image_array=None, geo_transform=None):
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        if image_array is not None:
            self._load_array(image_array)
        elif path:
            self._load_file(path)
        normalized_transform = normalize_geo_transform(geo_transform)
        if normalized_transform:
            self._geo_transform = normalized_transform
            self._has_geo_transform = True
        else:
            self._geo_transform = (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
            self._has_geo_transform = False
        self._fit_to_view()
        self.render()

    def load_blank(self, width=1600, height=1000, color=(24, 27, 38)):
        """Create a blank image-backed workspace so vector editing can receive mouse events."""
        arr = np.full((height, width, 3), color, dtype=np.uint8)
        self.load(image_array=arr)

    def clear_image(self):
        self._pil_image = None
        self._tk_img = None
        self._img_width = 0
        self._img_height = 0
        self._overview_scale = 1.0
        self._has_geo_transform = False
        self._overlays.clear()
        self._canvas.delete("all")
        self._update_zoom_label()

    def _load_file(self, path):
        self._pil_image = Image.open(path).convert("RGB")
        w, h = self._pil_image.size
        self._img_width, self._img_height = w, h
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > 100 or max(w, h) > 8000:
            s = 2048 / max(w, h)
            self._pil_image = self._pil_image.resize((int(w * s), int(h * s)), Image.LANCZOS)
            self._overview_scale = s
        else:
            self._overview_scale = 1.0

    def _load_array(self, arr):
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        elif arr.shape[2] == 4:
            arr = arr[:, :, :3]
        arr = np.ascontiguousarray(arr)
        self._pil_image = Image.fromarray(arr)
        h, w = arr.shape[:2]
        self._img_width, self._img_height = w, h
        self._overview_scale = 1.0

    # ==================== 叠加层 ====================
    @staticmethod
    def _to_tk_color(c):
        """将 matplotlib tuple (0.2,0.5,0.8) 或 hex '#3388cc' 转为 tkinter 颜色"""
        if isinstance(c, tuple):
            r, g, b = [max(0, min(255, int(v * 255))) for v in c[:3]]
            return f"#{r:02x}{g:02x}{b:02x}"
        return str(c) if c else ""

    def clear_overlays(self):
        self._overlays.clear()

    def add_point(self, x, y, color="#ff4444", radius=5, label=""):
        self._overlays.append(("point", float(x), float(y), color, radius, label))

    def add_rect(self, x1, y1, x2, y2, color="#00ff66", width=2, label=""):
        self._overlays.append(
            ("rect", float(x1), float(y1), float(x2), float(y2), color, width, label)
        )

    def add_polygon(self, points, color="#ffaa00", fill="", width=2, label=""):
        self._overlays.append(
            ("polygon", [(float(p[0]), float(p[1])) for p in points], color, fill, width, label)
        )

    def add_line(self, points, color="#ffaa00", width=2, label=""):
        self._overlays.append(
            ("line", [(float(p[0]), float(p[1])) for p in points], color, width, label)
        )

    def add_text(self, x, y, text, color="#ffffff", size=10):
        self._overlays.append(("text", float(x), float(y), str(text), color, size))

    # ==================== 坐标转换 ====================
    def pixel_to_geo(self, px, py):
        x0, dx, _, y0, _, dy = self._geo_transform
        return (x0 + px * dx, y0 + py * dy)

    def canvas_to_image(self, cx, cy):
        px = (cx - self._offset_x) / self._zoom / self._overview_scale
        py = (cy - self._offset_y) / self._zoom / self._overview_scale
        return (px, py)

    def _to_canvas(self, px, py):
        s = self._overview_scale
        return (self._offset_x + px * s * self._zoom, self._offset_y + py * s * self._zoom)

    # ==================== 视图操作 ====================
    def _fit_to_view(self):
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 4:
            cw = 600
        if ch < 4:
            ch = 400
        if self._img_width > 0:
            s = max(self._overview_scale, 1e-9)
            display_w = self._img_width * s
            display_h = self._img_height * s
            self._zoom = min(cw / display_w, ch / display_h, 1.0 / s) * 0.9
            dw = self._img_width * self._zoom * self._overview_scale
            dh = self._img_height * self._zoom * self._overview_scale
            self._offset_x = (cw - dw) / 2
            self._offset_y = (ch - dh) / 2
            self._update_zoom_label()

    def fit_to_view(self):
        if not self._pil_image:
            return
        self._fit_to_view()
        self.render()

    def zoom_actual(self):
        if not self._pil_image:
            return
        cw = self._canvas.winfo_width() or 600
        ch = self._canvas.winfo_height() or 400
        self._zoom = 1.0 / max(self._overview_scale, 1e-9)
        self._zoom = max(self._min_zoom, min(self._max_zoom, self._zoom))
        self._offset_x = (cw - self._img_width * self._overview_scale * self._zoom) / 2
        self._offset_y = (ch - self._img_height * self._overview_scale * self._zoom) / 2
        self.render()

    def zoom_by(self, factor, center=None):
        if not self._pil_image:
            return
        nz = self._zoom * factor
        if nz < self._min_zoom or nz > self._max_zoom:
            return
        if center is None:
            center = (
                (self._canvas.winfo_width() or 600) / 2,
                (self._canvas.winfo_height() or 400) / 2,
            )
        mx, my = center
        self._offset_x = mx - (mx - self._offset_x) * factor
        self._offset_y = my - (my - self._offset_y) * factor
        self._zoom = nz
        self.render()

    def export_screenshot(self):
        if not self._pil_image:
            notify(self, "暂无可导出的影像", "warning")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG 图像", "*.png"), ("JPEG 图像", "*.jpg")],
            title="导出截图",
        )
        if not path:
            return
        try:
            self._pil_image.save(path)
            notify(self, f"截图已导出：{path}", "success")
        except Exception as e:
            notify(self, f"截图导出失败：{e}", "error")

    def _update_zoom_label(self):
        if hasattr(self, "_zoom_label"):
            effective = self._zoom * self._overview_scale * 100
            self._zoom_label.configure(text=f"{effective:.0f}%")

    def _on_resize(self, event):
        if self._pil_image:
            self.render()

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start:
            self._offset_x += event.x - self._drag_start[0]
            self._offset_y += event.y - self._drag_start[1]
            self._drag_start = (event.x, event.y)
            self.render()

    def _on_wheel(self, event):
        factor = 1.15 if event.delta > 0 else 1.0 / 1.15
        self.zoom_by(factor, center=(event.x, event.y))

    def _on_motion(self, event):
        if self._on_coord_change and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            if 0 <= px < self._img_width and 0 <= py < self._img_height:
                if self._has_geo_transform:
                    gx, gy = self.pixel_to_geo(px, py)
                    self._on_coord_change(f"像素: ({px:.1f}, {py:.1f})  地图: ({gx:.4f}, {gy:.4f})")
                else:
                    self._on_coord_change(f"像素: ({px:.1f}, {py:.1f})")
            else:
                self._on_coord_change("")

    # ==================== 渲染 ====================
    def _on_left_press(self, event):
        if self._on_mouse_down and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            if 0 <= px < self._img_width and 0 <= py < self._img_height:
                self._on_mouse_down(px, py, event)

    def _on_left_release(self, event):
        if self._on_mouse_up and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            self._on_mouse_up(px, py, event)

    def _on_left_drag(self, event):
        if self._on_mouse_move and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            self._on_mouse_move(px, py, event)

    def _on_left_dblclick(self, event):
        if self._on_dblclick and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            if 0 <= px < self._img_width and 0 <= py < self._img_height:
                self._on_dblclick(px, py)

    def _on_right_click(self, event):
        if self._on_mouse_down and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            self._on_mouse_down(px, py, {"type": "right"})

    def render(self):
        if not self._pil_image:
            self._canvas.delete("all")
            return
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        if cw < 4 or ch < 4:
            return
        self._canvas.delete("all")
        self._update_zoom_label()
        z, s = self._zoom, self._overview_scale
        vx, vy = -self._offset_x / z, -self._offset_y / z
        vw, vh = cw / z, ch / z
        iw, ih = self._pil_image.width, self._pil_image.height
        sx = max(0, int(vx))
        sy = max(0, int(vy))
        sx2 = min(iw, int(vx + vw) + 1)
        sy2 = min(ih, int(vy + vh) + 1)
        if sx2 <= sx or sy2 <= sy:
            return
        try:
            crop = self._pil_image.crop((sx, sy, sx2, sy2))
            dw, dh = int((sx2 - sx) * z), int((sy2 - sy) * z)
            if dw < 1 or dh < 1:
                return
            if dw > 4096 or dh > 4096:
                r = min(4096 / dw, 4096 / dh)
                dw, dh = int(dw * r), int(dh * r)
            crop = crop.resize((dw, dh), Image.LANCZOS)
            self._tk_img = ImageTk.PhotoImage(crop)
            self._canvas.create_image(
                self._offset_x + sx * z, self._offset_y + sy * z, anchor="nw", image=self._tk_img
            )
        except Exception:
            pass

        # 叠加层
        for ov in self._overlays:
            k = ov[0]
            if k == "point":
                cx, cy = self._to_canvas(ov[1], ov[2])
                r = ov[4]
                self._canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r, outline=self._to_tk_color(ov[3]), width=2
                )
                if ov[5]:
                    self._canvas.create_text(
                        cx + r + 4, cy, text=ov[5], anchor="w", fill="#fff", font=("Consolas", 9)
                    )
            elif k == "rect":
                cx1, cy1 = self._to_canvas(ov[1], ov[2])
                cx2, cy2 = self._to_canvas(ov[3], ov[4])
                self._canvas.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=self._to_tk_color(ov[5]), width=ov[6]
                )
                if ov[7]:
                    self._canvas.create_text(
                        cx1 + 4,
                        cy1 - 10,
                        text=ov[7],
                        anchor="w",
                        fill=self._to_tk_color(ov[5]),
                        font=("Consolas", 9),
                    )
            elif k == "polygon":
                pts = [c for p in ov[1] for c in self._to_canvas(*p)]
                if len(pts) >= 4:
                    self._canvas.create_polygon(
                        pts,
                        outline=self._to_tk_color(ov[2]),
                        fill=self._to_tk_color(ov[3]) or "",
                        width=ov[4],
                    )
            elif k == "line":
                pts = [c for p in ov[1] for c in self._to_canvas(*p)]
                if len(pts) >= 4:
                    self._canvas.create_line(pts, fill=self._to_tk_color(ov[2]), width=ov[3])
                    if ov[4]:
                        self._canvas.create_text(
                            pts[0] + 4,
                            pts[1] - 10,
                            text=ov[4],
                            anchor="w",
                            fill=self._to_tk_color(ov[2]),
                            font=("Consolas", 9),
                        )
            elif k == "text":
                cx, cy = self._to_canvas(ov[1], ov[2])
                self._canvas.create_text(
                    cx, cy, text=ov[3], anchor="sw", fill=ov[4], font=("Microsoft YaHei", ov[5])
                )
