"""3D viewer tab – layer management sidebar and interactive viewport.

Provides the full 3D scene tab: layer tree with visibility/color/point-size
controls, import buttons, processing commands, camera presets, and a progress bar.
The right panel holds a Viewer3DViewport driven by SceneService.

Replaces the Tkinter-based ui/viewer_3d_tab.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.scene_graph import ColorMode, LayerType, SceneLayer
from ui_qt.i18n import tr
from ui_qt.task_runner import run_background
from ui_qt.widgets.viewer_3d_viewport import Viewer3DViewport


# Key for storing layer data in tree widget items
_LAYER_ROLE = Qt.ItemDataRole.UserRole
_LAYER_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class Viewer3DTab(QWidget):
    """3D viewer tab with layer sidebar and interactive viewport.

    Signals:
        statusMessage(message): emitted for status-bar messages.
    """

    statusMessage = Signal(str)

    # Camera presets -----------------------------------------------------------------
    _CAMERA_PRESETS: dict[str, str | tuple] = {
        "top":          "xy",
        "front":        "xz",
        "side":         "yz",
        "perspective":  "iso",
    }

    # ------------------------------------------------------------------
    def __init__(self, ctx: Any = None, parent: QWidget | None = None):
        super().__init__(parent)

        from application.scene_service import SceneService

        self._ctx = ctx
        self._scene_service: SceneService | None = (
            ctx.scene_service if ctx else None
        )

        self._build_ui()
        self._connect_signals()
        self._sync_from_scene()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # -- splitter: sidebar | viewport ------------------------------------------
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left panel (sidebar scroll area)
        self._sidebar = self._build_sidebar()
        self._splitter.addWidget(self._sidebar)

        # Right panel (viewport + progress)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._viewport = Viewer3DViewport(right_panel)
        right_layout.addWidget(self._viewport, stretch=1)

        self._progress_bar = QProgressBar(right_panel)
        self._progress_bar.setRange(0, 0)  # indeterminate by default
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        right_layout.addWidget(self._progress_bar)

        self._splitter.addWidget(right_panel)
        self._splitter.setStretchFactor(0, 0)  # sidebar doesn't stretch
        self._splitter.setStretchFactor(1, 1)  # viewport stretches
        self._splitter.setSizes([280, 800])

        root_layout.addWidget(self._splitter)

    def _build_sidebar(self) -> QScrollArea:
        """Construct the left sidebar inside a QScrollArea."""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(240)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # -- Layers group ----------------------------------------------------------
        layers_group = QGroupBox(tr("viewer_3d.layers"))
        self._layers_group = layers_group
        layers_layout = QVBoxLayout(layers_group)

        # Layer tree
        self._layer_tree = QTreeWidget()
        self._layer_tree.setHeaderLabels([
            tr("viewer_3d.col_name"),
            tr("viewer_3d.col_visible"),
            tr("viewer_3d.col_size"),
        ])
        self._layer_tree.setColumnCount(3)
        self._layer_tree.setRootIsDecorated(False)
        self._layer_tree.setSelectionMode(
            self._layer_tree.selectionMode().SingleSelection
        )
        self._layer_tree.setIndentation(0)
        self._layer_tree.header().setStretchLastSection(False)
        self._layer_tree.header().resizeSection(0, 120)
        self._layer_tree.header().resizeSection(1, 50)
        self._layer_tree.header().resizeSection(2, 60)
        self._layer_tree.setMinimumHeight(120)

        layers_layout.addWidget(self._layer_tree)

        # Layer controls row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(4)

        self._clr_label = QLabel(tr("viewer_3d.color_mode"))
        self._color_mode_combo = QComboBox()
        for mode in ColorMode:
            self._color_mode_combo.addItem(mode.value.capitalize(), mode.value)
        ctrl_layout.addWidget(self._clr_label)
        ctrl_layout.addWidget(self._color_mode_combo, stretch=1)

        self._size_label = QLabel(tr("viewer_3d.point_size"))
        self._point_size_spin = QDoubleSpinBox()
        self._point_size_spin.setRange(0.1, 50.0)
        self._point_size_spin.setValue(2.0)
        self._point_size_spin.setDecimals(1)
        self._point_size_spin.setSingleStep(0.5)
        ctrl_layout.addWidget(self._size_label)
        ctrl_layout.addWidget(self._point_size_spin)

        layers_layout.addLayout(ctrl_layout)

        btn_layout = QHBoxLayout()
        self._remove_layer_btn = QPushButton(tr("viewer_3d.remove_layer"))
        self._clear_scene_btn = QPushButton(tr("viewer_3d.clear_scene"))
        btn_layout.addWidget(self._remove_layer_btn)
        btn_layout.addWidget(self._clear_scene_btn)
        layers_layout.addLayout(btn_layout)

        layout.addWidget(layers_group)

        # -- Import group ----------------------------------------------------------
        import_group = QGroupBox(tr("viewer_3d.import"))
        self._import_group = import_group
        import_layout = QVBoxLayout(import_group)

        self._import_pcd_btn = QPushButton(tr("viewer_3d.import_point_cloud"))
        self._import_mesh_btn = QPushButton(tr("viewer_3d.import_mesh"))
        self._import_dem_btn = QPushButton(tr("viewer_3d.import_dem"))

        import_layout.addWidget(self._import_pcd_btn)
        import_layout.addWidget(self._import_mesh_btn)
        import_layout.addWidget(self._import_dem_btn)

        layout.addWidget(import_group)

        # -- Processing group ------------------------------------------------------
        proc_group = QGroupBox(tr("viewer_3d.processing"))
        self._proc_group = proc_group
        proc_layout = QGridLayout(proc_group)

        self._voxel_btn = QPushButton(tr("viewer_3d.voxel_downsample"))
        self._voxel_spin = QDoubleSpinBox()
        self._voxel_spin.setRange(0.01, 10.0)
        self._voxel_spin.setValue(0.1)
        self._voxel_spin.setDecimals(3)
        self._voxel_spin.setSingleStep(0.05)

        self._sor_btn = QPushButton(tr("viewer_3d.sor_filter"))
        self._ground_btn = QPushButton(tr("viewer_3d.ground_filter"))
        self._normals_btn = QPushButton(tr("viewer_3d.compute_normals"))
        self._crop_btn = QPushButton(tr("viewer_3d.crop"))

        proc_layout.addWidget(self._voxel_btn, 0, 0)
        proc_layout.addWidget(self._voxel_spin, 0, 1)
        proc_layout.addWidget(self._sor_btn, 1, 0)
        proc_layout.addWidget(self._ground_btn, 1, 1)
        proc_layout.addWidget(self._normals_btn, 2, 0)
        proc_layout.addWidget(self._crop_btn, 2, 1)

        layout.addWidget(proc_group)

        # -- Camera presets group --------------------------------------------------
        cam_group = QGroupBox(tr("viewer_3d.camera"))
        self._cam_group = cam_group
        cam_layout = QGridLayout(cam_group)

        self._cam_top_btn = QPushButton(tr("viewer_3d.cam_top"))
        self._cam_front_btn = QPushButton(tr("viewer_3d.cam_front"))
        self._cam_side_btn = QPushButton(tr("viewer_3d.cam_side"))
        self._cam_persp_btn = QPushButton(tr("viewer_3d.cam_perspective"))
        self._cam_fit_btn = QPushButton(tr("viewer_3d.cam_fit"))

        cam_layout.addWidget(self._cam_top_btn, 0, 0)
        cam_layout.addWidget(self._cam_front_btn, 0, 1)
        cam_layout.addWidget(self._cam_side_btn, 1, 0)
        cam_layout.addWidget(self._cam_persp_btn, 1, 1)
        cam_layout.addWidget(self._cam_fit_btn, 2, 0, 1, 2)

        layout.addWidget(cam_group)

        # -- GPU status ------------------------------------------------------------
        self._gpu_status_label = QLabel(tr("viewer_3d.gpu_checking"))
        self._gpu_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gpu_status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._gpu_status_label)

        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Layer tree
        self._layer_tree.currentItemChanged.connect(self._on_layer_selection_changed)

        # Layer controls
        self._color_mode_combo.currentIndexChanged.connect(self._on_color_mode_changed)
        self._point_size_spin.valueChanged.connect(self._on_point_size_changed)

        # Layer buttons
        self._remove_layer_btn.clicked.connect(self._on_remove_layer)
        self._clear_scene_btn.clicked.connect(self._on_clear_scene)

        # Import
        self._import_pcd_btn.clicked.connect(self._on_import_pointcloud)
        self._import_mesh_btn.clicked.connect(self._on_import_mesh)
        self._import_dem_btn.clicked.connect(self._on_import_dem)

        # Processing
        self._voxel_btn.clicked.connect(self._on_voxel_downsample)
        self._sor_btn.clicked.connect(self._on_sor_filter)
        self._ground_btn.clicked.connect(self._on_ground_filter)
        self._normals_btn.clicked.connect(self._on_compute_normals)
        self._crop_btn.clicked.connect(self._on_crop)

        # Camera presets
        self._cam_top_btn.clicked.connect(lambda: self._set_camera("top"))
        self._cam_front_btn.clicked.connect(lambda: self._set_camera("front"))
        self._cam_side_btn.clicked.connect(lambda: self._set_camera("side"))
        self._cam_persp_btn.clicked.connect(lambda: self._set_camera("perspective"))
        self._cam_fit_btn.clicked.connect(self._viewport.reset_camera)

        # Viewport
        self._viewport.pointPicked.connect(self._on_point_picked)

    # ------------------------------------------------------------------
    # Scene sync
    # ------------------------------------------------------------------

    def _sync_from_scene(self) -> None:
        """Rebuild the layer tree from the current scene graph."""
        self._layer_tree.clear()

        if self._scene_service is None:
            self._update_gpu_status()
            return

        scene = self._scene_service.scene
        for layer in scene.layers:
            self._add_layer_item(layer)

        self._update_gpu_status()
        self._rebuild_viewport()

    def _add_layer_item(self, layer: SceneLayer) -> QTreeWidgetItem:
        """Create and insert a tree item for *layer*."""
        item = QTreeWidgetItem(self._layer_tree)
        item.setData(0, _LAYER_ROLE, layer)
        item.setData(0, _LAYER_ID_ROLE, layer.id)

        # Name column
        item.setText(0, layer.name or layer.id[:8])

        # Visible column (checkbox-like)
        visible_text = "✓" if layer.visible else "✗"
        item.setText(1, visible_text)

        # Size column
        item.setText(2, f"{layer.point_size:.1f}")

        self._layer_tree.addTopLevelItem(item)
        return item

    def _rebuild_viewport(self) -> None:
        """Re-add all visible layers to the viewport."""
        self._viewport.clear()

        if self._scene_service is None:
            return

        scene = self._scene_service.scene
        self._viewport.set_background_color(scene.background_color)
        self._viewport.set_origin_grid(
            visible=scene.show_origin_grid,
            size=scene.grid_size,
            spacing=scene.grid_spacing,
        )

        for layer in scene.get_visible_layers():
            if layer.geometry is None:
                continue
            self._add_layer_to_viewport(layer)

        self._viewport.reset_camera()

    def _add_layer_to_viewport(self, layer: SceneLayer) -> None:
        """Add a single visible layer to the viewport."""
        geom = layer.geometry
        if geom is None:
            return

        import open3d as o3d

        if layer.layer_type == LayerType.POINT_CLOUD:
            if isinstance(geom, o3d.geometry.PointCloud):
                pts = np.asarray(geom.points, dtype=np.float32)
                colors = self._resolve_colors(layer)
                self._viewport.add_point_cloud(
                    points=pts,
                    colors=colors,
                    name=layer.id,
                    point_size=layer.point_size,
                )

        elif layer.layer_type == LayerType.MESH:
            self._viewport.add_mesh(
                mesh=geom,
                name=layer.id,
                opacity=layer.opacity,
            )

        elif layer.layer_type == LayerType.DEM:
            if isinstance(geom, o3d.geometry.PointCloud):
                pts = np.asarray(geom.points, dtype=np.float32)
                colors = self._resolve_colors(layer)
                self._viewport.add_point_cloud(
                    points=pts,
                    colors=colors,
                    name=layer.id,
                    point_size=1.5,
                )

    def _resolve_colors(
        self, layer: SceneLayer
    ) -> np.ndarray | None:
        """Produce per-point colours from the layer's colour mode."""
        geom = layer.geometry
        if geom is None:
            return None

        import open3d as o3d

        points = np.asarray(geom.points, dtype=np.float32)
        if points.size == 0:
            return None

        mode = layer.color_mode

        if mode == ColorMode.RGB and geom.has_colors():
            return np.asarray(geom.colors, dtype=np.float32)

        if mode == ColorMode.CLASSIFICATION:
            import open3d as o3d
            from core.scene_graph import get_classification_color

            field = layer.classification_field or "classification"
            if field in layer.attributes:
                cls_ids = np.asarray(layer.attributes[field], dtype=np.int32)
            elif hasattr(geom, "point") and hasattr(geom.point, field):
                cls_ids = np.asarray(getattr(geom.point, field), dtype=np.int32)
            else:
                return np.full((len(points), 3), layer.single_color, dtype=np.float32)

            colors = np.zeros((len(cls_ids), 3), dtype=np.float32)
            for cid in np.unique(cls_ids):
                clr = get_classification_color(int(cid))
                colors[cls_ids == cid] = clr
            return colors

        if mode == ColorMode.ELEVATION:
            from core.scene_graph import apply_colormap

            z = points[:, 2]
            return apply_colormap(z, cmap_name=layer.colormap or "viridis")

        if mode == ColorMode.INTENSITY:
            from core.scene_graph import apply_colormap

            field = "intensity"
            if field in layer.attributes:
                vals = np.asarray(layer.attributes[field], dtype=np.float32)
            else:
                vals = points[:, 2]
            return apply_colormap(vals, cmap_name=layer.colormap or "plasma")

        # SINGLE or fallback
        return np.full((len(points), 3), layer.single_color, dtype=np.float32)

    # ------------------------------------------------------------------
    # Layer tree interaction
    # ------------------------------------------------------------------

    def _selected_layer(self) -> SceneLayer | None:
        """Return the currently selected layer, or None."""
        items = self._layer_tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, _LAYER_ROLE)

    def _selected_layer_id(self) -> str | None:
        """Return the ID of the currently selected layer, or None."""
        items = self._layer_tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, _LAYER_ID_ROLE)

    def _on_layer_selection_changed(self) -> None:
        """Update controls to reflect the selected layer's state."""
        layer = self._selected_layer()
        enabled = layer is not None

        self._color_mode_combo.setEnabled(enabled)
        self._point_size_spin.setEnabled(enabled)
        self._remove_layer_btn.setEnabled(enabled)

        if layer is None:
            return

        # Set color mode combo
        index = self._color_mode_combo.findData(layer.color_mode.value)
        if index >= 0:
            self._color_mode_combo.blockSignals(True)
            self._color_mode_combo.setCurrentIndex(index)
            self._color_mode_combo.blockSignals(False)

        # Set point size
        self._point_size_spin.blockSignals(True)
        self._point_size_spin.setValue(layer.point_size)
        self._point_size_spin.blockSignals(False)

    def _on_color_mode_changed(self) -> None:
        layer = self._selected_layer()
        if layer is None:
            return

        mode_value = self._color_mode_combo.currentData()
        layer.color_mode = ColorMode(mode_value)
        self._rebuild_viewport()

    def _on_point_size_changed(self, value: float) -> None:
        layer = self._selected_layer()
        if layer is None:
            return

        layer.point_size = value

        # Update tree item
        items = self._layer_tree.selectedItems()
        if items:
            items[0].setText(2, f"{value:.1f}")

        self._rebuild_viewport()

    def _on_remove_layer(self) -> None:
        layer_id = self._selected_layer_id()
        if layer_id is None or self._scene_service is None:
            return

        self._scene_service.remove_layer(layer_id)
        self._sync_from_scene()
        self.statusMessage.emit(tr("viewer_3d.layer_removed"))

    def _on_clear_scene(self) -> None:
        if self._scene_service is None:
            return

        self._scene_service.clear_scene()
        self._sync_from_scene()
        self.statusMessage.emit(tr("viewer_3d.scene_cleared"))

    # ------------------------------------------------------------------
    # Import handlers
    # ------------------------------------------------------------------

    def _on_import_pointcloud(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("viewer_3d.import_point_cloud"),
            "",
            tr("filter.pointcloud"),
        )
        if not path:
            return
        self._run_async(self._do_import_pointcloud, path, tr("viewer_3d.importing_pcd"))

    def _on_import_mesh(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("viewer_3d.import_mesh"),
            "",
            tr("filter.mesh"),
        )
        if not path:
            return
        self._run_async(self._do_import_mesh, path, tr("viewer_3d.importing_mesh"))

    def _on_import_dem(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("viewer_3d.import_dem"),
            "",
            tr("filter.dem"),
        )
        if not path:
            return
        self._run_async(self._do_import_dem, path, tr("viewer_3d.importing_dem"))

    def _do_import_pointcloud(self, path_str: str) -> None:
        if self._scene_service is None:
            return
        data = self._scene_service.load_pointcloud(path_str)
        if data is None or data.points is None:
            raise RuntimeError(tr("viewer_3d.import_failed"))

        layer = SceneLayer(
            name=Path(path_str).stem,
            layer_type=LayerType.POINT_CLOUD,
            source_path=path_str,
            geometry=data.points,
            point_count=len(data.points.points),
            point_size=2.0,
        )
        if data.colors is not None:
            layer.attributes["colors"] = np.asarray(data.colors, dtype=np.float32)
        if data.classifications is not None:
            layer.attributes["classification"] = np.asarray(
                data.classifications, dtype=np.int32
            )
            layer.color_mode = ColorMode.CLASSIFICATION
        self._scene_service.add_layer(layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.imported", name=Path(path_str).name)
        )

    def _do_import_mesh(self, path_str: str) -> None:
        if self._scene_service is None:
            return
        mesh = self._scene_service.load_mesh(path_str)
        if mesh is None:
            raise RuntimeError(tr("viewer_3d.import_failed"))

        try:
            face_count = len(mesh.triangles)
        except Exception:
            face_count = 0

        layer = SceneLayer(
            name=Path(path_str).stem,
            layer_type=LayerType.MESH,
            source_path=path_str,
            geometry=mesh,
            face_count=face_count,
        )
        self._scene_service.add_layer(layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.imported", name=Path(path_str).name)
        )

    def _do_import_dem(self, path_str: str) -> None:
        if self._scene_service is None:
            return

        import open3d as o3d

        # Attempt to read as raster DEM, convert to point cloud
        try:
            from osgeo import gdal
            ds = gdal.Open(path_str)
            if ds is None:
                raise RuntimeError(tr("viewer_3d.import_failed"))
            band = ds.GetRasterBand(1)
            dem = band.ReadAsArray().astype(np.float32)
            gt = ds.GetGeoTransform()
            # Build x, y, z arrays
            rows, cols = dem.shape
            x_coords = np.linspace(gt[0], gt[0] + cols * gt[1], cols, dtype=np.float32)
            y_coords = np.linspace(gt[3], gt[3] + rows * gt[5], rows, dtype=np.float32)
            xx, yy = np.meshgrid(x_coords, y_coords)
            # subsample for performance
            step = max(1, min(cols, rows) // 2000)
            xx = xx[::step, ::step].ravel()
            yy = yy[::step, ::step].ravel()
            zz = dem[::step, ::step].ravel()
            mask = ~np.isnan(zz)
            pts = np.column_stack([xx[mask], yy[mask], zz[mask]])
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(pts)
        except ImportError:
            # Fallback: treat as point cloud
            data = self._scene_service.load_pointcloud(path_str)
            if data is None or data.points is None:
                raise RuntimeError(tr("viewer_3d.import_failed"))
            pcd = data.points

        colors = self._elevation_colors(np.asarray(pcd.points, dtype=np.float32))
        pcd.colors = o3d.utility.Vector3dVector(colors)

        layer = SceneLayer(
            name=Path(path_str).stem,
            layer_type=LayerType.DEM,
            source_path=path_str,
            geometry=pcd,
            point_count=len(pcd.points),
            color_mode=ColorMode.ELEVATION,
            colormap="terrain",
        )
        self._scene_service.add_layer(layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.imported", name=Path(path_str).name)
        )

    # ------------------------------------------------------------------
    # Processing handlers
    # ------------------------------------------------------------------

    def _on_voxel_downsample(self) -> None:
        layer = self._selected_layer()
        if layer is None or self._scene_service is None:
            return
        voxel_size = self._voxel_spin.value()

        self._run_async(
            self._do_voxel_downsample,
            {"layer": layer, "voxel_size": voxel_size},
            tr("viewer_3d.processing"),
        )

    def _on_sor_filter(self) -> None:
        layer = self._selected_layer()
        if layer is None or self._scene_service is None:
            return

        self._run_async(
            self._do_sor_filter,
            {"layer": layer},
            tr("viewer_3d.processing"),
        )

    def _on_ground_filter(self) -> None:
        layer = self._selected_layer()
        if layer is None or self._scene_service is None:
            return

        self._run_async(
            self._do_ground_filter,
            {"layer": layer},
            tr("viewer_3d.processing"),
        )

    def _on_compute_normals(self) -> None:
        layer = self._selected_layer()
        if layer is None or self._scene_service is None:
            return

        self._run_async(
            self._do_compute_normals,
            {"layer": layer},
            tr("viewer_3d.processing"),
        )

    def _on_crop(self) -> None:
        layer = self._selected_layer()
        if layer is None or self._scene_service is None:
            return
        self.statusMessage.emit(tr("viewer_3d.crop_not_implemented"))

    def _do_voxel_downsample(self, args: dict) -> None:
        from core.pointcloud_io import PointCloudData

        layer: SceneLayer = args["layer"]
        voxel_size: float = args["voxel_size"]

        if layer.geometry is None:
            return

        import open3d as o3d

        if isinstance(layer.geometry, o3d.geometry.PointCloud):
            pcd = layer.geometry

            data = PointCloudData(
                points=np.asarray(pcd.points, dtype=np.float32),
                colors=np.asarray(pcd.colors, dtype=np.float32) if pcd.has_colors() else None,
                classifications=np.asarray(
                    layer.attributes.get("classification", np.zeros(len(pcd.points), dtype=np.int32)),
                    dtype=np.int32,
                ),
            )
        else:
            return

        filtered = self._scene_service.voxel_downsample(data, voxel_size)
        new_pcd = o3d.geometry.PointCloud()
        new_pcd.points = o3d.utility.Vector3dVector(filtered.points)
        if filtered.colors is not None:
            new_pcd.colors = o3d.utility.Vector3dVector(filtered.colors)

        new_layer_name = f"{layer.name}_voxel_{voxel_size:.2f}"
        new_layer = SceneLayer(
            name=new_layer_name,
            layer_type=LayerType.POINT_CLOUD,
            source_path=layer.source_path,
            geometry=new_pcd,
            point_count=len(new_pcd.points),
            point_size=layer.point_size,
            color_mode=layer.color_mode,
            colormap=layer.colormap,
        )
        if filtered.classifications is not None:
            new_layer.attributes["classification"] = filtered.classifications

        self._scene_service.add_layer(new_layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.process_done", name=new_layer_name)
        )

    def _do_sor_filter(self, args: dict) -> None:
        from core.pointcloud_io import PointCloudData

        layer: SceneLayer = args["layer"]

        if layer.geometry is None:
            return

        import open3d as o3d

        if isinstance(layer.geometry, o3d.geometry.PointCloud):
            pcd = layer.geometry
            data = PointCloudData(
                points=np.asarray(pcd.points, dtype=np.float32),
                colors=np.asarray(pcd.colors, dtype=np.float32) if pcd.has_colors() else None,
            )
        else:
            return

        data = self._scene_service.statistical_filter(data)
        new_pcd = o3d.geometry.PointCloud()
        new_pcd.points = o3d.utility.Vector3dVector(data.points)
        if data.colors is not None:
            new_pcd.colors = o3d.utility.Vector3dVector(data.colors)

        new_layer_name = f"{layer.name}_sor"
        new_layer = SceneLayer(
            name=new_layer_name,
            layer_type=LayerType.POINT_CLOUD,
            source_path=layer.source_path,
            geometry=new_pcd,
            point_count=len(new_pcd.points),
            point_size=layer.point_size,
            color_mode=layer.color_mode,
            colormap=layer.colormap,
        )
        self._scene_service.add_layer(new_layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.process_done", name=new_layer_name)
        )

    def _do_ground_filter(self, args: dict) -> None:
        from core.pointcloud_io import PointCloudData

        layer: SceneLayer = args["layer"]

        if layer.geometry is None:
            return

        import open3d as o3d

        if isinstance(layer.geometry, o3d.geometry.PointCloud):
            pcd = layer.geometry
            data = PointCloudData(
                points=np.asarray(pcd.points, dtype=np.float32),
                colors=np.asarray(pcd.colors, dtype=np.float32) if pcd.has_colors() else None,
            )
        else:
            return

        data = self._scene_service.cloth_simulation_filter(data)
        new_pcd = o3d.geometry.PointCloud()
        new_pcd.points = o3d.utility.Vector3dVector(data.points)
        if data.colors is not None:
            new_pcd.colors = o3d.utility.Vector3dVector(data.colors)

        new_layer_name = f"{layer.name}_ground"
        new_layer = SceneLayer(
            name=new_layer_name,
            layer_type=LayerType.POINT_CLOUD,
            source_path=layer.source_path,
            geometry=new_pcd,
            point_count=len(new_pcd.points),
            point_size=layer.point_size,
            color_mode=layer.color_mode,
            colormap=layer.colormap,
        )
        self._scene_service.add_layer(new_layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.process_done", name=new_layer_name)
        )

    def _do_compute_normals(self, args: dict) -> None:
        from core.pointcloud_io import PointCloudData

        layer: SceneLayer = args["layer"]

        if layer.geometry is None:
            return

        import open3d as o3d

        if isinstance(layer.geometry, o3d.geometry.PointCloud):
            pcd = layer.geometry
            data = PointCloudData(
                points=np.asarray(pcd.points, dtype=np.float32),
                colors=np.asarray(pcd.colors, dtype=np.float32) if pcd.has_colors() else None,
            )
        else:
            return

        data = self._scene_service.estimate_normals(data)
        new_pcd = o3d.geometry.PointCloud()
        new_pcd.points = o3d.utility.Vector3dVector(data.points)
        if data.colors is not None:
            new_pcd.colors = o3d.utility.Vector3dVector(data.colors)

        new_layer_name = f"{layer.name}_normals"
        new_layer = SceneLayer(
            name=new_layer_name,
            layer_type=LayerType.POINT_CLOUD,
            source_path=layer.source_path,
            geometry=new_pcd,
            point_count=len(new_pcd.points),
            point_size=layer.point_size,
            color_mode=layer.color_mode,
            colormap=layer.colormap,
        )
        self._scene_service.add_layer(new_layer)
        self._sync_from_scene()
        self.statusMessage.emit(
            tr("viewer_3d.process_done", name=new_layer_name)
        )

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _set_camera(self, preset_name: str) -> None:
        """Apply a named camera preset."""
        position = self._CAMERA_PRESETS.get(preset_name)
        if position:
            self._viewport.set_camera_position(position)
            self.statusMessage.emit(
                tr("viewer_3d.camera_set", preset=preset_name)
            )

    # ------------------------------------------------------------------
    # Point picking
    # ------------------------------------------------------------------

    def _on_point_picked(self, x: float, y: float, z: float) -> None:
        self.statusMessage.emit(
            tr("viewer_3d.point_picked", x=f"{x:.3f}", y=f"{y:.3f}", z=f"{z:.3f}")
        )

    # ------------------------------------------------------------------
    # GPU status
    # ------------------------------------------------------------------

    def _update_gpu_status(self) -> None:
        if self._scene_service is None:
            self._gpu_status_label.setText(tr("viewer_3d.gpu_unavailable"))
            return
        available = self._scene_service.gpu_available()
        if available:
            self._gpu_status_label.setText(tr("viewer_3d.gpu_available"))
            self._gpu_status_label.setStyleSheet("color: #4a4; font-size: 11px;")
        else:
            self._gpu_status_label.setText(tr("viewer_3d.gpu_unavailable"))
            self._gpu_status_label.setStyleSheet("color: #a84; font-size: 11px;")

    # ------------------------------------------------------------------
    # Background task runner
    # ------------------------------------------------------------------

    def _run_async(self, target_fn, arg, description: str = "") -> None:
        """Run a processing operation in the background with progress indicator."""
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._set_sidebar_enabled(False)
        self.statusMessage.emit(description)

        def _work():
            if callable(target_fn) and arg is None:
                return target_fn()
            elif callable(target_fn):
                return target_fn(arg)
            else:
                return None

        def _on_done(result):
            self._progress_bar.setVisible(False)
            self._set_sidebar_enabled(True)
            self.statusMessage.emit(tr("viewer_3d.done"))

        def _on_error(err: str):
            self._progress_bar.setVisible(False)
            self._set_sidebar_enabled(True)
            self.statusMessage.emit(
                tr("viewer_3d.error", error=err)
            )

        run_background(
            target=_work,
            on_done=_on_done,
            on_error=_on_error,
            parent=self,
        )

    def _set_sidebar_enabled(self, enabled: bool) -> None:
        """Enable or disable sidebar controls during processing."""
        self._layer_tree.setEnabled(enabled)
        self._color_mode_combo.setEnabled(enabled)
        self._point_size_spin.setEnabled(enabled)
        self._remove_layer_btn.setEnabled(enabled)
        self._clear_scene_btn.setEnabled(enabled)
        self._import_pcd_btn.setEnabled(enabled)
        self._import_mesh_btn.setEnabled(enabled)
        self._import_dem_btn.setEnabled(enabled)
        self._voxel_btn.setEnabled(enabled)
        self._sor_btn.setEnabled(enabled)
        self._ground_btn.setEnabled(enabled)
        self._normals_btn.setEnabled(enabled)
        self._crop_btn.setEnabled(enabled)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        # Group boxes
        self._layers_group.setTitle(tr("viewer_3d.layers"))
        self._import_group.setTitle(tr("viewer_3d.import"))
        self._proc_group.setTitle(tr("viewer_3d.processing"))
        self._cam_group.setTitle(tr("viewer_3d.camera"))

        # Tree headers
        self._layer_tree.setHeaderLabels([
            tr("viewer_3d.col_name"), tr("viewer_3d.col_visible"), tr("viewer_3d.col_size")
        ])

        # Controls labels — rebuild color mode combo (data-preserving)
        color_idx = self._color_mode_combo.currentIndex()
        self._color_mode_combo.clear()
        for mode in ColorMode:
            self._color_mode_combo.addItem(mode.value.capitalize(), mode.value)
        if color_idx >= 0 and color_idx < self._color_mode_combo.count():
            self._color_mode_combo.setCurrentIndex(color_idx)

        # Buttons — layers
        self._remove_layer_btn.setText(tr("viewer_3d.remove_layer"))
        self._clear_scene_btn.setText(tr("viewer_3d.clear_scene"))

        # Buttons — import
        self._import_pcd_btn.setText(tr("viewer_3d.import_point_cloud"))
        self._import_mesh_btn.setText(tr("viewer_3d.import_mesh"))
        self._import_dem_btn.setText(tr("viewer_3d.import_dem"))

        # Buttons — processing
        self._voxel_btn.setText(tr("viewer_3d.voxel_downsample"))
        self._sor_btn.setText(tr("viewer_3d.sor_filter"))
        self._ground_btn.setText(tr("viewer_3d.ground_filter"))
        self._normals_btn.setText(tr("viewer_3d.compute_normals"))
        self._crop_btn.setText(tr("viewer_3d.crop"))

        # Camera presets
        self._cam_top_btn.setText(tr("viewer_3d.cam_top"))
        self._cam_front_btn.setText(tr("viewer_3d.cam_front"))
        self._cam_side_btn.setText(tr("viewer_3d.cam_side"))
        self._cam_persp_btn.setText(tr("viewer_3d.cam_perspective"))
        self._cam_fit_btn.setText(tr("viewer_3d.cam_fit"))

        # Layout labels
        self._clr_label.setText(tr("viewer_3d.color_mode"))
        self._size_label.setText(tr("viewer_3d.point_size"))

        self._sync_from_scene()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return serializable state for project persistence."""
        if self._scene_service is None:
            return {}
        return {
            "scene": self._scene_service.scene.to_dict(),
            "splitter_sizes": self._splitter.sizes(),
        }

    def set_state(self, state: dict) -> None:
        """Restore state from project persistence."""
        if self._scene_service is None or not state:
            return

        scene_data = state.get("scene")
        if scene_data:
            self._scene_service.scene.from_dict(scene_data)

        sizes = state.get("splitter_sizes")
        if sizes and len(sizes) == 2:
            self._splitter.setSizes([int(s) for s in sizes])

        self._sync_from_scene()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _elevation_colors(points: np.ndarray) -> np.ndarray:
        """Map Z-coordinate to terrain-like colours."""
        from core.scene_graph import apply_colormap

        z = points[:, 2]
        return apply_colormap(z, cmap_name="terrain")
