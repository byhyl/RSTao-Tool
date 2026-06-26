"""QGraphicsView-based raster image viewer with zoom/pan/overlays.

Replaces ui/raster_viewer.py (CTkCanvas-based).
"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QGraphicsItemGroup,
)

from domain.raster import GeoTransform


def _ndarray_to_qpixmap(arr: np.ndarray) -> QPixmap:
    """Convert numpy array (H, W) or (H, W, C) to QPixmap."""
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        if arr.dtype == np.float32 or arr.dtype == np.float64:
            vmin, vmax = np.percentile(arr, [2, 98])
            arr = np.clip((arr - vmin) / (vmax - vmin + 1e-8) * 255, 0, 255).astype(np.uint8)
        else:
            arr = arr.astype(np.uint8)

    if arr.ndim == 2:
        h, w = arr.shape
        qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
    elif arr.ndim == 3 and arr.shape[2] == 3:
        h, w, _ = arr.shape
        qimg = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
    elif arr.ndim == 3 and arr.shape[2] == 4:
        h, w, _ = arr.shape
        qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    else:
        h, w = arr.shape[:2]
        qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)

    return QPixmap.fromImage(qimg)


class RasterViewer(QGraphicsView):
    """GIS raster viewer with zoom/pan/overlays and coordinate display.

    Signals:
        cursorMoved(px, py, geo_x, geo_y): emitted on mouse move
        clicked(px, py, geo_x, geo_y): emitted on left click
        viewChanged(zoom, offset_x, offset_y): emitted on zoom/pan
    """

    cursorMoved = Signal(int, int, float, float)
    clicked = Signal(int, int, float, float)
    viewChanged = Signal(float, float, float)
    displayParamsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Scene
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # Image layers
        self._base_item: QGraphicsPixmapItem | None = None
        self._overlay_group: QGraphicsItemGroup | None = None

        # State
        self._geo_transform: GeoTransform | None = None
        self._img_width: int = 0
        self._img_height: int = 0
        self._pil_image: np.ndarray | None = None
        self._current_pixmap: QPixmap | None = None
        self._zoom: float = 1.0

        # Multi-band / display params
        self._raw_data: np.ndarray | None = None
        self._band_indices: list[int] = [1, 2, 3]
        self._display_mode: str = "rgb"
        self._low_percent: float = 2.0
        self._high_percent: float = 98.0
        self._file_path: str | None = None

        # View settings
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

    # -- loading ---------------------------------------------------------------

    def load(self, path: str | None = None, image_array: np.ndarray | None = None) -> None:
        """Load an image from file path or numpy array."""
        if path:
            self._file_path = str(path)
            size_bytes = os.path.getsize(str(path))
            from data.image_io import read_image
            arr = read_image(str(path))
            if arr is not None:
                h, w = arr.shape[:2]
                size_mb = size_bytes / (1024 * 1024)
                if size_mb > 100 or max(w, h) > 8000:
                    scale = 2048 / max(w, h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    import cv2
                    arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
                self._raw_data = None
                self._load_array(arr)
        elif image_array is not None:
            self._file_path = None
            self._load_array(image_array)

    def load_from_array(self, arr: np.ndarray) -> None:
        self._raw_data = None
        self._file_path = None
        self._load_array(arr)

    def load_raster(self, path: str) -> None:
        """Load a raster file retaining multi-band raw data for band selection / stretch."""
        from data.image_io import read_raster_data, get_image_metadata

        self._file_path = str(path)
        size_bytes = os.path.getsize(str(path))
        meta = get_image_metadata(str(path))
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > 100 or max(meta.get("width", 0), meta.get("height", 0)) > 8000:
            arr = read_raster_data(str(path), preserve_dtype=False)
            h, w = arr.shape[:2]
            scale = 2048 / max(w, h)
            import cv2
            arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
            self._raw_data = None
            self._band_indices = [1, 2, 3]
            self._load_array(arr)
        else:
            arr = read_raster_data(str(path), preserve_dtype=True)
            self._raw_data = arr
            if arr.ndim == 3:
                self._band_indices = list(range(1, min(arr.shape[2], 3) + 1))
            self._render_display_image()
            self._overlay_group = QGraphicsItemGroup()
            self._scene.addItem(self._overlay_group)
            self._zoom = 1.0
            self.resetTransform()
            self.fit_to_view()

    def _load_array(self, arr: np.ndarray) -> None:
        self._clear_scene()
        self._pil_image = arr
        self._img_height, self._img_width = arr.shape[:2]
        self._current_pixmap = _ndarray_to_qpixmap(arr)
        self._base_item = self._scene.addPixmap(self._current_pixmap)
        self._overlay_group = QGraphicsItemGroup()
        self._scene.addItem(self._overlay_group)
        self._scene.setSceneRect(QRectF(0, 0, self._img_width, self._img_height))
        self._zoom = 1.0
        self.resetTransform()
        self.fit_to_view()

    def load_blank(self, width: int, height: int, color: tuple[int, int, int] = (255, 255, 255)) -> None:
        arr = np.full((height, width, 3), color, dtype=np.uint8)
        self._load_array(arr)

    def clear_image(self) -> None:
        self._clear_scene()
        self._pil_image = None
        self._current_pixmap = None
        self._img_width = 0
        self._img_height = 0
        self._geo_transform = None
        self._raw_data = None
        self._file_path = None

    def _clear_scene(self) -> None:
        self._scene.clear()
        self._base_item = None
        self._overlay_group = None

    # -- geo transform ---------------------------------------------------------

    def set_geo_transform(self, gt: GeoTransform | None, crs: str = "") -> None:
        self._geo_transform = gt

    # -- coordinate transforms -------------------------------------------------

    def pixel_to_geo(self, px: float, py: float) -> tuple[float, float]:
        if self._geo_transform is None:
            return (px, py)
        gt = self._geo_transform
        x = gt.x0 + px * gt.dx + py * gt.rx
        y = gt.y0 + px * gt.ry + py * gt.dy
        return (x, y)

    def canvas_to_image(self, cx: float, cy: float) -> tuple[int, int]:
        pt = self.mapToScene(int(cx), int(cy))
        return (int(pt.x()), int(pt.y()))

    # -- display rendering -------------------------------------------------------

    def _render_display_image(self) -> None:
        """Rebuild display pixmap from raw data using current band/mode/stretch."""
        if self._raw_data is None:
            return
        arr = self._raw_data
        n_bands = arr.shape[2] if arr.ndim == 3 else 1

        # Extract selected bands (1-based → 0-based)
        if arr.ndim == 3 and n_bands >= 1:
            indices = [i - 1 for i in self._band_indices if 0 < i <= n_bands]
            if not indices:
                indices = [0]
            arr = np.ascontiguousarray(arr[:, :, indices])

        from data.image_io import make_preview
        preview = make_preview(arr, self._low_percent, self._high_percent)

        # Grayscale conversion
        if self._display_mode == "grayscale" and preview.ndim == 3 and preview.shape[2] >= 3:
            preview = np.dot(preview[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)

        pixmap = _ndarray_to_qpixmap(preview)
        self._update_display_pixmap(pixmap)

    def _update_display_pixmap(self, pixmap: QPixmap) -> None:
        self._current_pixmap = pixmap
        self._img_height = pixmap.height()
        self._img_width = pixmap.width()
        if self._base_item is not None:
            self._base_item.setPixmap(pixmap)
        else:
            self._clear_scene()
            self._base_item = self._scene.addPixmap(pixmap)
            self._overlay_group = QGraphicsItemGroup()
            self._scene.addItem(self._overlay_group)
        self._scene.setSceneRect(QRectF(0, 0, self._img_width, self._img_height))

    # -- band / mode / stretch ---------------------------------------------------

    def set_band_indices(self, indices: list[int]) -> None:
        if self._raw_data is None or self._raw_data.ndim < 3:
            return
        max_band = self._raw_data.shape[2]
        self._band_indices = [i for i in indices if 0 < i <= max_band]
        if not self._band_indices:
            self._band_indices = [1]
        self._render_display_image()
        self.displayParamsChanged.emit()

    def set_band(self, band_index: int) -> None:
        self.set_band_indices([band_index])

    def band_count(self) -> int:
        if self._raw_data is not None and self._raw_data.ndim == 3:
            return self._raw_data.shape[2]
        return 1

    def set_display_mode(self, mode: str) -> None:
        if mode not in ("rgb", "grayscale"):
            return
        self._display_mode = mode
        self._render_display_image()
        self.displayParamsChanged.emit()

    def set_percentile_stretch(self, low_percent: float, high_percent: float) -> None:
        self._low_percent = max(0.0, min(low_percent, 100.0))
        self._high_percent = max(0.0, min(high_percent, 100.0))
        if self._high_percent <= self._low_percent:
            self._high_percent = self._low_percent + 1.0
        self._render_display_image()
        self.displayParamsChanged.emit()

    def export_screenshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Screenshot",
            "",
            "PNG Image (*.png);;JPEG Image (*.jpg)",
        )
        if not path:
            return
        pixmap = self.grab()
        pixmap.save(path)

    # -- properties --------------------------------------------------------------

    @property
    def display_mode(self) -> str:
        return self._display_mode

    @property
    def band_indices(self) -> list[int]:
        return list(self._band_indices)

    @property
    def percentile_stretch(self) -> tuple[float, float]:
        return (self._low_percent, self._high_percent)

    @property
    def raw_band_count(self) -> int:
        return self.band_count()

    @property
    def file_path(self) -> str | None:
        return self._file_path

    # -- view control ----------------------------------------------------------

    def fit_to_view(self) -> None:
        if self._base_item:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()
            self.viewChanged.emit(self._zoom, 0.0, 0.0)

    def zoom_actual(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self.viewChanged.emit(self._zoom, 0.0, 0.0)

    def zoom_by(self, factor: float) -> None:
        if factor > 1.0 and self._zoom * factor > 20.0:
            return
        if factor < 1.0 and self._zoom * factor < 0.01:
            return
        self.scale(factor, factor)
        self._zoom = self.transform().m11()
        self.viewChanged.emit(self._zoom, 0.0, 0.0)

    # -- overlays --------------------------------------------------------------

    def add_point(self, x: float, y: float, color: str = "red",
                  radius: float = 3.0, label: str = "") -> None:
        item = self._scene.addEllipse(
            x - radius, y - radius, radius * 2, radius * 2,
            QPen(QColor(color)), QBrush(QColor(color))
        )
        if self._overlay_group:
            item.setParentItem(self._overlay_group)
        if label:
            text = self._scene.addSimpleText(label, QFont("Arial", 9))
            text.setPos(x + radius + 2, y + radius + 2)
            text.setBrush(QBrush(QColor(color)))
            if self._overlay_group:
                text.setParentItem(self._overlay_group)

    def add_rect(self, x1: float, y1: float, x2: float, y2: float,
                 color: str = "red", width: float = 2.0, label: str = "") -> None:
        item = self._scene.addRect(
            x1, y1, x2 - x1, y2 - y1,
            QPen(QColor(color), width)
        )
        if self._overlay_group:
            item.setParentItem(self._overlay_group)
        if label:
            text = self._scene.addSimpleText(label, QFont("Arial", 9))
            text.setPos(x1, y1 - 18)
            text.setBrush(QBrush(QColor(color)))
            if self._overlay_group:
                text.setParentItem(self._overlay_group)

    def add_polygon(self, points: list[tuple[float, float]],
                    color: str = "red", width: float = 2.0, fill: bool = False) -> None:
        qpoints = [QPointF(x, y) for x, y in points]
        poly = QGraphicsPolygonItem()
        poly.setPolygon(qpoints)
        if fill:
            poly.setBrush(QBrush(QColor(color, alpha=60)))
        poly.setPen(QPen(QColor(color), width))
        self._scene.addItem(poly)
        if self._overlay_group:
            poly.setParentItem(self._overlay_group)

    def add_line(self, x1: float, y1: float, x2: float, y2: float,
                 color: str = "red", width: float = 2.0) -> None:
        item = self._scene.addLine(x1, y1, x2, y2, QPen(QColor(color), width))
        if self._overlay_group:
            item.setParentItem(self._overlay_group)

    def add_text(self, x: float, y: float, text: str, color: str = "yellow",
                 size: int = 10) -> None:
        item = self._scene.addSimpleText(text, QFont("Arial", size))
        item.setPos(x, y)
        item.setBrush(QBrush(QColor(color)))
        if self._overlay_group:
            item.setParentItem(self._overlay_group)

    def clear_overlays(self) -> None:
        if self._overlay_group:
            self._scene.removeItem(self._overlay_group)
        self._overlay_group = QGraphicsItemGroup()
        self._scene.addItem(self._overlay_group)

    # -- mouse events ----------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.zoom_by(factor)
        self._emit_cursor_pos(event.position().x(), event.position().y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            px, py = self.canvas_to_image(event.position().x(), event.position().y())
            gx, gy = self.pixel_to_geo(px, py)
            self.clicked.emit(px, py, gx, gy)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._emit_cursor_pos(event.position().x(), event.position().y())
        super().mouseMoveEvent(event)

    def _emit_cursor_pos(self, wx: float, wy: float) -> None:
        px, py = self.canvas_to_image(wx, wy)
        gx, gy = self.pixel_to_geo(px, py)
        self.cursorMoved.emit(px, py, gx, gy)

    # -- properties ------------------------------------------------------------

    @property
    def image_width(self) -> int:
        return self._img_width

    @property
    def image_height(self) -> int:
        return self._img_height

    @property
    def zoom_level(self) -> float:
        return self._zoom

    @property
    def has_image(self) -> bool:
        return self._base_item is not None
