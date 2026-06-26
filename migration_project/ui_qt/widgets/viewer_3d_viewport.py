"""PyVista Qt viewport widget with interactive 3D rendering.

Provides a QWidget-based 3D viewport using pyvistaqt.QtInteractor when available,
falling back to offscreen rendering to QImage when pyvistaqt is not installed.

Replaces the Tkinter-based 3D viewer from ui/viewer_3d.py.
"""

from __future__ import annotations

import io
import numpy as np

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QImage, QPixmap, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ui_qt.i18n import tr

# ---------------------------------------------------------------------------
# PyVista / pyvistaqt availability detection
# ---------------------------------------------------------------------------
try:
    from pyvistaqt import QtInteractor
    HAS_PVQT = True
except ImportError:
    HAS_PVQT = False

try:
    import pyvista as pv
    HAS_PV = True
except ImportError:
    HAS_PV = False


try:
    import open3d as o3d
    HAS_O3D = True
except ImportError:
    HAS_O3D = False


class Viewer3DViewport(QWidget):
    """PyVista 3D viewport wrapped in a QWidget.

    Signals:
        pointPicked(x, y, z): emitted when a click hits geometry (world-space coords).

    Public methods:
        add_mesh(mesh, name, color, opacity, **kwargs)
        add_point_cloud(points, colors, name, point_size, **kwargs)
        clear()
        reset_camera()
        screenshot() -> bytes
        set_background_color(color)
        remove_actor(name)
    """

    pointPicked = Signal(float, float, float)
    viewChanged = Signal()

    # ------------------------------------------------------------------
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._actors: dict[str, object] = {}
        self._bg_color: tuple[float, float, float, float] = (0.12, 0.12, 0.14, 1.0)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        if HAS_PVQT and HAS_PV:
            self._init_pvqt_viewport()
        elif HAS_PV:
            self._init_offscreen_viewport()
        else:
            self._init_fallback_viewport()

        self.setMinimumSize(QSize(320, 240))

    # ------------------------------------------------------------------
    # Initialization paths
    # ------------------------------------------------------------------

    def _init_pvqt_viewport(self) -> None:
        """Full interactive viewport using pyvistaqt."""
        import pyvista as pv
        import pyvistaqt

        self._interactor: QtInteractor = pyvistaqt.QtInteractor(self)
        self._layout.addWidget(self._interactor)

        self._plotter = self._interactor
        self._plotter.set_background(
            [self._bg_color[0], self._bg_color[1], self._bg_color[2]]
        )

        # Enable basic handlers
        self._plotter.enable_point_picking(
            callback=self._on_point_picked,
            show_message=False,
            show_point=False,
            pickable_window=True,
            tolerance=0.01,
        )

        self._plotter.show_grid(
            xtitle="X", ytitle="Y", ztitle="Z",
            color=[0.3, 0.3, 0.3, 0.3],
            grid=True,
        )

        self._is_interactive = True

    def _init_offscreen_viewport(self) -> None:
        """Offscreen pyvista renderer drawn into a QLabel."""
        import pyvista as pv

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: #1e1e24;")
        self._image_label.setSizePolicy(
            self._image_label.sizePolicy().horizontalPolicy(),
            self._image_label.sizePolicy().verticalPolicy(),
        )
        self._scroll_area.setWidget(self._image_label)
        self._layout.addWidget(self._scroll_area)

        self._plotter = pv.Plotter(off_screen=True)
        self._plotter.set_background(
            [self._bg_color[0], self._bg_color[1], self._bg_color[2]]
        )
        self._plotter.show_grid(
            xtitle="X", ytitle="Y", ztitle="Z",
            color=[0.3, 0.3, 0.3, 0.3],
            grid=True,
        )
        self._plotter.camera_position = "xy"

        self._is_interactive = False
        self._dirty = True

    def _init_fallback_viewport(self) -> None:
        """Placeholder when neither pyvistaqt nor pyvista is available."""
        label = QLabel(self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setText("PyVista not installed.\nInstall pyvista and pyvistaqt for 3D view.")
        label.setStyleSheet("color: #888; font-size: 14px;")
        self._layout.addWidget(label)

        self._plotter = None
        self._is_interactive = False
        self._dirty = False

    # ------------------------------------------------------------------
    # Camera helpers
    # ------------------------------------------------------------------

    def _refresh_offscreen(self) -> None:
        """Re-render the offscreen plotter and update the QLabel."""
        if self._is_interactive or self._plotter is None:
            return

        self._plotter.render()
        img = self._plotter.image  # (H, W, 4) RGBA uint8

        if img is not None:
            h, w, _ = img.shape
            qimg = QImage(img.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            self._image_label.setPixmap(pixmap)

        self._dirty = False

    def _mark_dirty(self) -> None:
        if not self._is_interactive:
            self._dirty = True
            self._refresh_offscreen()

    def _on_point_picked(self, point) -> None:
        """Internal callback for pyvista point picking."""
        if point is not None and hasattr(point, "__iter__"):
            try:
                coords = tuple(float(c) for c in point[:3])
            except (TypeError, IndexError, ValueError):
                coords = tuple(float(point[i]) for i in range(min(3, len(point))))
            self.pointPicked.emit(coords[0], coords[1], coords[2])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_mesh(
        self,
        mesh: object,
        name: str = "mesh",
        color: str | tuple[float, float, float] | None = None,
        opacity: float = 1.0,
        show_edges: bool = False,
        **kwargs,
    ) -> None:
        """Add a mesh (pyvista, Open3D, or trimesh) to the viewport.

        Args:
            mesh: The mesh geometry. Open3D TriangleMesh is converted to pyvista.
            name: Unique actor name (replaces existing actor with the same name).
            color: Solid color for the mesh.
            opacity: Opacity (0..1).
            show_edges: Whether to draw edge lines.
        """
        if self._plotter is None:
            return

        pv_mesh = self._to_pyvista_mesh(mesh)
        if pv_mesh is None:
            return

        # Remove previous actor with the same name
        self.remove_actor(name)

        if color is None:
            color = (0.3, 0.7, 1.0)

        actor = self._plotter.add_mesh(
            pv_mesh,
            name=name,
            color=color,
            opacity=opacity,
            show_edges=show_edges,
            **kwargs,
        )
        self._actors[name] = actor
        self._mark_dirty()

    def add_point_cloud(
        self,
        points: np.ndarray,
        colors: np.ndarray | None = None,
        name: str = "pointcloud",
        point_size: float = 2.0,
        **kwargs,
    ) -> None:
        """Add a point cloud to the viewport.

        Args:
            points: (N, 3) float32/float64 array.
            colors: (N, 3) float32/float64 array (0..1 or 0..255).  If
                    None, default cyan is used.
            name: Unique actor name.
            point_size: Per-point size.
        """
        if self._plotter is None:
            return

        pv_pcd = self._points_to_pyvista(points, colors)

        self.remove_actor(name)

        actor = self._plotter.add_points(
            pv_pcd,
            name=name,
            point_size=point_size,
            render_points_as_spheres=(point_size >= 3),
            **kwargs,
        )
        self._actors[name] = actor
        self._mark_dirty()

    def clear(self) -> None:
        """Remove all actors from the viewport."""
        if self._plotter is None:
            return

        self._plotter.clear()
        self._actors.clear()

        # Re-apply background and grid after clear
        self._plotter.set_background(
            [self._bg_color[0], self._bg_color[1], self._bg_color[2]]
        )
        if not self._is_interactive:
            self._plotter.show_grid(
                xtitle="X", ytitle="Y", ztitle="Z",
                color=[0.3, 0.3, 0.3, 0.3],
                grid=True,
            )
            self._plotter.camera_position = "xy"

        self._refresh_offscreen()

    def remove_actor(self, name: str) -> None:
        """Remove a named actor."""
        if name in self._actors:
            self._plotter.remove_actor(self._actors[name])
            del self._actors[name]
            self._mark_dirty()

    def reset_camera(self) -> None:
        """Reset the camera to fit all actors."""
        if self._plotter is None:
            return

        try:
            if self._is_interactive:
                self._plotter.reset_camera()
            else:
                self._plotter.reset_camera()
                self._mark_dirty()
        except Exception:
            pass

    def set_camera_position(self, position: str | tuple) -> None:
        """Set a preset camera position.

        Args:
            position: One of 'xy', 'xz', 'yz', 'yx', 'zx', 'zy', 'iso',
                      or a tuple (camera_pos, focal_point, view_up).
        """
        if self._plotter is None:
            return

        try:
            self._plotter.camera_position = position
            self._mark_dirty()
        except Exception:
            pass

    def screenshot(self) -> bytes | None:
        """Return a PNG screenshot of the current view as bytes."""
        if self._plotter is None:
            return None

        try:
            if self._is_interactive:
                buf = io.BytesIO()
                self._plotter.screenshot(buf, return_img=False)
                return buf.getvalue()
            else:
                self._plotter.render()
                buf = io.BytesIO()
                self._plotter.screenshot(buf, return_img=False)
                return buf.getvalue()
        except Exception:
            return None

    def set_background_color(
        self, color: tuple[float, float, float, float] | str
    ) -> None:
        """Set the viewport background colour.

        Args:
            color: Either an (R, G, B, A) float tuple (0..1) or a QColor name string.
        """
        if self._plotter is None:
            return

        if isinstance(color, str):
            qc = QColor(color)
            if qc.isValid():
                self._bg_color = (
                    qc.redF(),
                    qc.greenF(),
                    qc.blueF(),
                    qc.alphaF(),
                )
        elif isinstance(color, (tuple, list)) and len(color) >= 3:
            self._bg_color = (
                float(color[0]),
                float(color[1]),
                float(color[2]),
                float(color[3]) if len(color) >= 4 else 1.0,
            )

        self._plotter.set_background(
            [self._bg_color[0], self._bg_color[1], self._bg_color[2]]
        )
        self._mark_dirty()

    def set_origin_grid(self, visible: bool, size: float = 100.0,
                        spacing: float = 10.0) -> None:
        """Show or hide the origin grid."""
        if self._plotter is None:
            return
        try:
            if visible:
                self._plotter.show_grid(
                    xtitle="X", ytitle="Y", ztitle="Z",
                    color=[0.3, 0.3, 0.3, 0.3],
                    grid=True,
                )
            else:
                self._plotter.remove_bounds_axes()
        except Exception:
            pass
        self._mark_dirty()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._is_interactive and self._plotter is not None:
            self._plotter.window_size = (
                self._image_label.width(),
                self._image_label.height(),
            )
            self._mark_dirty()

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pyvista_mesh(obj) -> "pv.PolyData | None":
        """Convert an Open3D mesh or trimesh object to pyvista PolyData."""
        if HAS_PV and isinstance(obj, pv.DataSet):
            return obj

        if HAS_O3D and isinstance(obj, o3d.geometry.TriangleMesh):
            verts = np.asarray(obj.vertices, dtype=np.float32)
            faces = np.asarray(obj.triangles, dtype=np.int32)
            if faces.size == 0 or verts.size == 0:
                return None
            # pyvista faces: [3, i0, i1, i2, ...]
            pv_faces = np.hstack(
                [np.full((faces.shape[0], 1), 3, dtype=np.int32), faces]
            ).ravel()
            pv_mesh = pv.PolyData(verts, pv_faces)
            # Transfer vertex colors if present
            if obj.has_vertex_colors():
                vc = np.asarray(obj.vertex_colors, dtype=np.float32)
                pv_mesh.point_data["RGB"] = vc
            return pv_mesh

        # Attempt trimesh conversion
        try:
            import trimesh
            if isinstance(obj, trimesh.Trimesh):
                verts = np.asarray(obj.vertices, dtype=np.float32)
                faces = np.asarray(obj.faces, dtype=np.int32)
                if faces.size == 0 or verts.size == 0:
                    return None
                pv_faces = np.hstack(
                    [np.full((faces.shape[0], 1), 3, dtype=np.int32), faces]
                ).ravel()
                return pv.PolyData(verts, pv_faces)
        except ImportError:
            pass

        return None

    @staticmethod
    def _points_to_pyvista(
        pts: np.ndarray,
        clr: np.ndarray | None = None,
    ) -> "pv.PolyData":
        """Build a pyvista PolyData point cloud from arrays."""
        pts = np.asarray(pts, dtype=np.float32)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError("Points must be (N, 3)")

        pcd = pv.PolyData(pts)

        if clr is not None:
            clr = np.asarray(clr, dtype=np.float32)
            if clr.shape[0] != pts.shape[0]:
                raise ValueError(
                    f"Colors length {clr.shape[0]} != points {pts.shape[0]}"
                )
            # Auto-detect 0-255 range
            if clr.max() > 1.0:
                clr = clr / 255.0
            pcd.point_data["RGB"] = np.clip(clr, 0.0, 1.0)

        return pcd

    # ------------------------------------------------------------------
    # Interactive mouse events (for offscreen mode)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press in offscreen fallback – emits click on nearest point."""
        if self._is_interactive or self._plotter is None:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            try:
                self._plotter.render()
                pos = event.position()
                # Perform a simple screen-space ray cast
                from pyvista import _vtk
                x, y = int(pos.x()), int(pos.y())
                picker = _vtk.vtkPropPicker()
                renderer = self._plotter.renderer
                picker.Pick(x, y, 0, renderer)
                picked = picker.GetPickPosition()
                if len(picked) == 3 and any(picked):
                    self.pointPicked.emit(
                        float(picked[0]), float(picked[1]), float(picked[2])
                    )
            except Exception:
                pass

        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle zoom in offscreen fallback by adjusting camera scale."""
        if self._is_interactive or self._plotter is None:
            super().wheelEvent(event)
            return

        try:
            delta = event.angleDelta().y() / 120.0
            factor = 1.1 ** delta
            cam = self._plotter.camera
            cam.zoom(factor)
            self._mark_dirty()
        except Exception:
            pass

        super().wheelEvent(event)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_interactive(self) -> bool:
        """Whether the viewport supports full mouse interaction."""
        return self._is_interactive

    @property
    def has_renderer(self) -> bool:
        """Whether a functioning renderer is available."""
        return self._plotter is not None
