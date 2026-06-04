"""GIS 级栅格影像查看器 — 像素精度漫游 + 叠加层 + 大文件优化"""
import math
import os
import numpy as np
from PIL import Image, ImageTk
import customtkinter as ctk
from .theme import THEME


class RasterViewer(ctk.CTkFrame):
    """可漫游放缩的栅格影像查看器，支持点/框/多边形叠加层

    操作: 鼠标中键拖拽=平移 | 滚轮=缩放 | 悬停显示像素+地理坐标
    """

    def __init__(self, parent, on_coord_change=None, on_mouse_down=None, on_mouse_up=None, on_mouse_move=None, on_dblclick=None):
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
        self._overlays = []
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._zoom = 1.0
        self._min_zoom = 0.01
        self._max_zoom = 50.0
        self._drag_start = None
        self._tk_img = None

        self._canvas = ctk.CTkCanvas(self, bg=THEME["card"], highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill="both", expand=True)
        # 中键拖拽=平移, 滚轮=缩放
        self._canvas.bind("<Button-2>", self._on_press)
        self._canvas.bind("<B2-Motion>", self._on_drag)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Button-1>", self._on_left_press)
        self._canvas.bind("<B1-Motion>", self._on_left_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self._canvas.bind("<Double-Button-1>", self._on_left_dblclick)

    # ==================== 加载 ====================
    def load(self, path="", image_array=None, geo_transform=None):
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        if image_array is not None:
            self._load_array(image_array)
        elif path:
            self._load_file(path)
        if geo_transform:
            self._geo_transform = geo_transform
        self._fit_to_view()
        self.render()

    def _load_file(self, path):
        self._pil_image = Image.open(path).convert("RGB")
        w, h = self._pil_image.size
        self._img_width, self._img_height = w, h
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > 100 or max(w, h) > 8000:
            s = 2048 / max(w, h)
            self._pil_image = self._pil_image.resize((int(w*s), int(h*s)), Image.LANCZOS)
            self._overview_scale = s
        else:
            self._overview_scale = 1.0

    def _load_array(self, arr):
        if arr.ndim == 2:
            arr = np.stack([arr]*3, axis=-1)
        elif arr.shape[2] == 4:
            arr = arr[:,:,:3]
        arr = np.ascontiguousarray(arr)
        self._pil_image = Image.fromarray(arr)
        h, w = arr.shape[:2]
        self._img_width, self._img_height = w, h
        self._overview_scale = 1.0

    # ==================== 叠加层 ====================
    def clear_overlays(self):
        self._overlays.clear()

    def add_point(self, x, y, color="#ff4444", radius=5, label=""):
        self._overlays.append(("point", float(x), float(y), color, radius, label))

    def add_rect(self, x1, y1, x2, y2, color="#00ff66", width=2, label=""):
        self._overlays.append(("rect", float(x1), float(y1), float(x2), float(y2), color, width, label))

    def add_polygon(self, points, color="#ffaa00", fill="", width=2, label=""):
        self._overlays.append(("polygon", [(float(p[0]), float(p[1])) for p in points], color, fill, width, label))

    def add_text(self, x, y, text, color="#ffffff", size=10):
        self._overlays.append(("text", float(x), float(y), str(text), color, size))

    # ==================== 坐标转换 ====================
    def pixel_to_geo(self, px, py):
        x0, dx, _, y0, _, dy = self._geo_transform
        return (x0 + px*dx, y0 + py*dy)

    def canvas_to_image(self, cx, cy):
        px = (cx - self._offset_x) / self._zoom / self._overview_scale
        py = (cy - self._offset_y) / self._zoom / self._overview_scale
        return (px, py)

    def _to_canvas(self, px, py):
        s = self._overview_scale
        return (self._offset_x + px*s*self._zoom, self._offset_y + py*s*self._zoom)

    # ==================== 视图操作 ====================
    def _fit_to_view(self):
        cw = self._canvas.winfo_width() or 600
        ch = self._canvas.winfo_height() or 400
        if self._img_width > 0:
            self._zoom = min(cw/self._img_width, ch/self._img_height, 1.0) * 0.9
            dw = self._img_width * self._zoom * self._overview_scale
            dh = self._img_height * self._zoom * self._overview_scale
            self._offset_x = (cw - dw) / 2
            self._offset_y = (ch - dh) / 2

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
        factor = 1.15 if event.delta > 0 else 1.0/1.15
        nz = self._zoom * factor
        if nz < self._min_zoom or nz > self._max_zoom:
            return
        mx, my = event.x, event.y
        self._offset_x = mx - (mx - self._offset_x)*factor
        self._offset_y = my - (my - self._offset_y)*factor
        self._zoom = nz
        self.render()

    def _on_motion(self, event):
        if self._on_coord_change and self._img_width > 0:
            px, py = self.canvas_to_image(event.x, event.y)
            if 0 <= px < self._img_width and 0 <= py < self._img_height:
                gx, gy = self.pixel_to_geo(px, py)
                self._on_coord_change(f"像素: ({px:.1f}, {py:.1f})  地理: ({gx:.4f}, {gy:.4f})")
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
    def render(self):
        if not self._pil_image:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 4 or ch < 4:
            return
        self._canvas.delete("all")
        z, s = self._zoom, self._overview_scale
        vx, vy = -self._offset_x/z, -self._offset_y/z
        vw, vh = cw/z, ch/z
        iw, ih = self._pil_image.width, self._pil_image.height
        sx = max(0, int(vx)); sy = max(0, int(vy))
        sx2 = min(iw, int(vx+vw)+1); sy2 = min(ih, int(vy+vh)+1)
        if sx2 <= sx or sy2 <= sy:
            return
        try:
            crop = self._pil_image.crop((sx, sy, sx2, sy2))
            dw, dh = int((sx2-sx)*z), int((sy2-sy)*z)
            if dw < 1 or dh < 1:
                return
            if dw > 4096 or dh > 4096:
                r = min(4096/dw, 4096/dh); dw, dh = int(dw*r), int(dh*r)
            crop = crop.resize((dw, dh), Image.LANCZOS)
            self._tk_img = ImageTk.PhotoImage(crop)
            self._canvas.create_image(self._offset_x+sx*z, self._offset_y+sy*z,
                                      anchor="nw", image=self._tk_img)
        except Exception:
            pass

        # 叠加层
        for ov in self._overlays:
            k = ov[0]
            if k == "point":
                cx, cy = self._to_canvas(ov[1], ov[2])
                r = ov[4]
                self._canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=ov[3], width=2)
                if ov[5]:
                    self._canvas.create_text(cx+r+4, cy, text=ov[5], anchor="w",
                                            fill="#fff", font=("Consolas", 9))
            elif k == "rect":
                cx1, cy1 = self._to_canvas(ov[1], ov[2])
                cx2, cy2 = self._to_canvas(ov[3], ov[4])
                self._canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=ov[5], width=ov[6])
                if ov[7]:
                    self._canvas.create_text(cx1+4, cy1-10, text=ov[7], anchor="w",
                                            fill=ov[5], font=("Consolas", 9))
            elif k == "polygon":
                pts = [c for p in ov[1] for c in self._to_canvas(*p)]
                if len(pts) >= 4:
                    self._canvas.create_polygon(pts, outline=ov[2], fill=ov[3] or "",
                                               width=ov[4])
            elif k == "text":
                cx, cy = self._to_canvas(ov[1], ov[2])
                self._canvas.create_text(cx, cy, text=ov[3], anchor="sw",
                                        fill=ov[4], font=("Microsoft YaHei", ov[5]))
