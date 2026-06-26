"""Vector editing tab -- QWidget with left panel tools + RasterViewer canvas.

Replaces ui/vector_tab.py (CTk-based).
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygonF,
    QAction,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.raster import GeoTransform
from domain.vector import GeometryType
from ..widgets.raster_viewer import RasterViewer
from ..widgets.raster_viewer_sidebar import RasterViewerSidebar

try:
    from ..helpers import notify, mark_project_dirty
except ImportError:
    def notify(widget: QWidget, message: str, level: str = "info", timeout: int = 5000) -> None:
        window = widget.window()
        if window and hasattr(window, "statusBar"):
            sb = window.statusBar()
            if sb:
                sb.showMessage(message, timeout)
                return
        if level == "error":
            QMessageBox.critical(widget, "Error", message)
        else:
            QMessageBox.information(widget, "Info", message)

    def mark_project_dirty(_main_window: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POINT_RADIUS = 3
LINE_WIDTH = 2
SELECT_TOLERANCE = 5
VERTEX_RADIUS = 4

# Per-geometry-type display colors
TYPE_COLORS = {
    GeometryType.POINT: QColor(255, 80, 80),          # red
    GeometryType.LINE_STRING: QColor(80, 160, 255),   # blue
    GeometryType.POLYGON: QColor(80, 255, 120),       # green
    GeometryType.MULTI_POINT: QColor(255, 80, 80),
    GeometryType.MULTI_LINE_STRING: QColor(80, 160, 255),
    GeometryType.MULTI_POLYGON: QColor(80, 255, 120),
    GeometryType.GEOMETRY_COLLECTION: QColor(200, 200, 200),
}

HIGHLIGHT_COLOR = QColor(255, 255, 0, 180)
VERTEX_COLOR = QColor(0, 200, 255)
VERTEX_SELECTED_COLOR = QColor(255, 200, 0)


# ---------------------------------------------------------------------------
class EditMode(Enum):
    SELECT = "select"
    MOVE = "move"
    DRAW_POINT = "draw_point"
    DRAW_LINE = "draw_line"
    DRAW_POLYGON = "draw_polygon"
    EDIT_VERTICES = "edit_vertices"


# Mapping from radio button object names to modes
BUTTON_MODE_MAP = {
    "select": EditMode.SELECT,
    "move": EditMode.MOVE,
    "draw_point": EditMode.DRAW_POINT,
    "draw_line": EditMode.DRAW_LINE,
    "draw_polygon": EditMode.DRAW_POLYGON,
    "edit_vertices": EditMode.EDIT_VERTICES,
}


# ---------------------------------------------------------------------------
# Command stack helpers (simple list-based undo/redo)
# ---------------------------------------------------------------------------
class _Command:
    """A reversible edit operation."""

    def do(self, tab: "VectorTab") -> None:
        raise NotImplementedError

    def undo(self, tab: "VectorTab") -> None:
        raise NotImplementedError


class _AddFeatureCommand(_Command):
    def __init__(self, dataset_id: str, feature: dict[str, Any]) -> None:
        self.dataset_id = dataset_id
        self.feature = feature

    def do(self, tab: "VectorTab") -> None:
        ds = tab._find_dataset(self.dataset_id)
        if ds is not None:
            ds["features"].append(self.feature)
            tab._rebuild_overlays()
            tab._refresh_property_editor()
            tab._refresh_layer_tree()

    def undo(self, tab: "VectorTab") -> None:
        ds = tab._find_dataset(self.dataset_id)
        if ds is not None:
            ds["features"] = [f for f in ds["features"] if f.get("id") != self.feature.get("id")]
            if tab._selected_feature_id == self.feature.get("id"):
                tab._selected_feature_id = None
            tab._rebuild_overlays()
            tab._refresh_property_editor()
            tab._refresh_layer_tree()


class _MoveFeatureCommand(_Command):
    def __init__(self, dataset_id: str, feature_id: str, dx: float, dy: float) -> None:
        self.dataset_id = dataset_id
        self.feature_id = feature_id
        self.dx = dx
        self.dy = dy

    def do(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            tab._translate_feature_geometry(feat, self.dx, self.dy)
            tab._rebuild_overlays()
            tab._refresh_property_editor()

    def undo(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            tab._translate_feature_geometry(feat, -self.dx, -self.dy)
            tab._rebuild_overlays()
            tab._refresh_property_editor()


class _MoveVertexCommand(_Command):
    def __init__(self, dataset_id: str, feature_id: str, vertex_index: int,
                 old_pt: tuple[float, float], new_pt: tuple[float, float]) -> None:
        self.dataset_id = dataset_id
        self.feature_id = feature_id
        self.vertex_index = vertex_index
        self.old_pt = old_pt
        self.new_pt = new_pt

    def do(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            tab._set_vertex(feat, self.vertex_index, self.new_pt)
            tab._rebuild_overlays()

    def undo(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            tab._set_vertex(feat, self.vertex_index, self.old_pt)
            tab._rebuild_overlays()


class _UpdatePropertyCommand(_Command):
    def __init__(self, dataset_id: str, feature_id: str, field: str,
                 old_value: Any, new_value: Any) -> None:
        self.dataset_id = dataset_id
        self.feature_id = feature_id
        self.field = field
        self.old_value = old_value
        self.new_value = new_value

    def do(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            props = feat.get("properties", {})
            props[self.field] = self.new_value
            tab._rebuild_overlays()
            tab._refresh_property_editor()

    def undo(self, tab: "VectorTab") -> None:
        feat = tab._find_feature(self.dataset_id, self.feature_id)
        if feat is not None:
            props = feat.get("properties", {})
            props[self.field] = self.old_value
            tab._rebuild_overlays()
            tab._refresh_property_editor()


# ---------------------------------------------------------------------------
class VectorTab(QWidget):
    """Vector editing tab with tools, layers, properties, and drawing canvas."""

    _DEFAULT_CANVAS_SIZE = 1024

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # App context (set externally after construction)
        self._ctx: Any = None

        # --- data model --------------------------------------------------------
        # Each dataset: {"id": str, "name": str, "path": str,
        #                 "geom_type": str, "features": [dict], "visible": bool}
        self._datasets: list[dict[str, Any]] = []

        # Track which dataset each feature belongs to (feature_id -> dataset_id)
        self._feature_owners: dict[str, str] = {}

        # Currently active dataset id (from layer tree selection)
        self._active_dataset_id: str | None = None

        # Selected feature id
        self._selected_feature_id: str | None = None

        # --- edit state --------------------------------------------------------
        self._mode: EditMode = EditMode.SELECT

        # Drawing state
        self._draw_points: list[tuple[float, float]] = []     # vertex accumulation
        self._last_mouse_pos: tuple[float, float] | None = None  # for rubber-band
        self._rubber_band_item: QGraphicsItem | None = None

        # Vertex editing state
        self._editing_vertex_dataset: str | None = None
        self._editing_vertex_feature: str | None = None
        self._editing_vertex_index: int = -1
        self._vertex_drag_start: tuple[float, float] | None = None

        # Move state
        self._move_start: tuple[float, float] | None = None
        self._move_start_feat_pos: tuple[float, float] | None = None
        self._move_snapshot_coords: list[tuple[float, float]] | None = None

        # --- base image --------------------------------------------------------
        self._base_image_path: str | None = None

        # --- undo / redo -------------------------------------------------------
        self._undo_stack: list[_Command] = []
        self._redo_stack: list[_Command] = []

        # --- overlays ----------------------------------------------------------
        # Groups of QGraphicsItems keyed by dataset_id; each entry is a
        # QGraphicsItemGroup parented to the viewer overlay group.
        self._layer_groups: dict[str, QGraphicsItemGroup] = {}
        # Highlight items (selection ring, vertex handles)
        self._highlight_items: list[QGraphicsItem] = []

        # --- build UI ----------------------------------------------------------
        self._build_ui()

    # ======================================================================
    # UI construction
    # ======================================================================

    def _build_ui(self) -> None:
        """Create the full splitter layout: left panel + right canvas."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- left panel (scrollable) -----------------------------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(280)
        left_scroll.setMaximumWidth(380)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._build_file_card())
        left_layout.addWidget(self._build_edit_tools_card())
        left_layout.addWidget(self._build_layer_card())
        left_layout.addWidget(self._build_property_card())
        left_layout.addStretch(1)

        left_scroll.setWidget(left_panel)

        # -- right panel: RasterViewer + sidebar -------------------------------
        self._viewer = RasterViewer()
        self._viewer.setMinimumSize(400, 300)

        right_panel = QWidget()
        right_layout = QHBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._viewer, 1)
        self._raster_sidebar = RasterViewerSidebar()
        self._raster_sidebar.attach(self._viewer)
        right_layout.addWidget(self._raster_sidebar)

        # Override mouse events on the viewer for custom vector interaction
        self._viewer.mousePressEvent = self._on_viewer_mouse_press    # type: ignore[assignment]
        self._viewer.mouseMoveEvent = self._on_viewer_mouse_move      # type: ignore[assignment]
        self._viewer.mouseReleaseEvent = self._on_viewer_mouse_release  # type: ignore[assignment]
        self._viewer.mouseDoubleClickEvent = self._on_viewer_double_click  # type: ignore[assignment]

        # Hook into the viewer's right-click via context menu
        self._viewer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._viewer.customContextMenuRequested.connect(self._on_viewer_context_menu)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # Initialize with a blank canvas
        self._viewer.load_blank(self._DEFAULT_CANVAS_SIZE, self._DEFAULT_CANVAS_SIZE,
                                (40, 40, 40))

    # ----- file operations card --------------------------------------------

    def _build_file_card(self) -> QGroupBox:
        group = QGroupBox(tr("vector.file_operations"))
        self._file_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._btn_load_shp = QPushButton(tr("vector.load_vector"))
        self._btn_load_shp.clicked.connect(self._on_load_vector)
        layout.addWidget(self._btn_load_shp)

        self._btn_new_layer = QPushButton(tr("vector.new_layer"))
        self._btn_new_layer.clicked.connect(self._on_new_layer)
        layout.addWidget(self._btn_new_layer)

        self._btn_load_base_image = QPushButton(tr("vector.load_base_image"))
        self._btn_load_base_image.clicked.connect(self._on_load_base_image)
        layout.addWidget(self._btn_load_base_image)

        self._export_label = QLabel(tr("vector.export_label"))
        layout.addWidget(self._export_label)
        export_row = QHBoxLayout()
        self._btn_export_shp = QPushButton(tr("vector.export_shp"))
        self._btn_export_shp.clicked.connect(lambda: self._on_export("shp"))
        self._btn_export_geojson = QPushButton(tr("vector.export_geojson"))
        self._btn_export_geojson.clicked.connect(lambda: self._on_export("geojson"))
        self._btn_export_dxf = QPushButton(tr("vector.export_dxf"))
        self._btn_export_dxf.clicked.connect(lambda: self._on_export("dxf"))
        export_row.addWidget(self._btn_export_shp)
        export_row.addWidget(self._btn_export_geojson)
        export_row.addWidget(self._btn_export_dxf)
        layout.addLayout(export_row)

        return group

    # ----- edit tools card ------------------------------------------------

    def _build_edit_tools_card(self) -> QGroupBox:
        group = QGroupBox(tr("vector.edit_tools"))
        self._edit_tools_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._tool_button_group = QButtonGroup(self)
        self._tool_button_group.setExclusive(True)

        tool_specs = [
            ("select", tr("vector.select")),
            ("move", tr("vector.move")),
            ("draw_point", tr("vector.draw_point")),
            ("draw_line", tr("vector.draw_line")),
            ("draw_polygon", tr("vector.draw_polygon")),
            ("edit_vertices", tr("vector.edit_vertices")),
        ]

        for obj_name, label in tool_specs:
            rb = QRadioButton(label)
            rb.setObjectName(obj_name)
            self._tool_button_group.addButton(rb)
            layout.addWidget(rb)

        self._tool_button_group.buttonToggled.connect(self._on_tool_changed)
        # default
        for btn in self._tool_button_group.buttons():
            if btn.objectName() == "select":
                btn.setChecked(True)
                break

        # undo / redo row
        undo_redo_row = QHBoxLayout()
        self._btn_undo = QPushButton(tr("vector.undo"))
        self._btn_undo.clicked.connect(self._undo)
        self._btn_redo = QPushButton(tr("vector.redo"))
        self._btn_redo.clicked.connect(self._redo)
        undo_redo_row.addWidget(self._btn_undo)
        undo_redo_row.addWidget(self._btn_redo)
        layout.addLayout(undo_redo_row)

        return group

    # ----- layer card ----------------------------------------------------

    def _build_layer_card(self) -> QGroupBox:
        group = QGroupBox(tr("vector.layer_management"))
        self._layer_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._layer_tree = QTreeWidget()
        self._layer_tree.setHeaderLabels([tr("vector.col_layer"), tr("vector.col_features")])
        self._layer_tree.header().setStretchLastSection(False)
        self._layer_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._layer_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._layer_tree.customContextMenuRequested.connect(self._on_layer_context_menu)
        self._layer_tree.itemChanged.connect(self._on_layer_visibility_changed)
        self._layer_tree.itemClicked.connect(self._on_layer_item_clicked)
        layout.addWidget(self._layer_tree)

        self._btn_delete_layer = QPushButton(tr("vector.delete_layer"))
        self._btn_delete_layer.clicked.connect(self._on_delete_layer)
        layout.addWidget(self._btn_delete_layer)

        return group

    # ----- property card ------------------------------------------------

    def _build_property_card(self) -> QGroupBox:
        group = QGroupBox(tr("vector.property_editor"))
        self._property_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._property_label = QLabel(tr("vector.no_feature_selected"))
        self._property_label.setWordWrap(True)
        layout.addWidget(self._property_label)

        self._property_table = QTableWidget(0, 2)
        self._property_table.setHorizontalHeaderLabels([tr("vector.col_field"), tr("vector.col_value")])
        self._property_table.horizontalHeader().setStretchLastSection(True)
        self._property_table.cellChanged.connect(self._on_property_cell_changed)
        layout.addWidget(self._property_table)

        prop_btn_row = QHBoxLayout()
        self._btn_add_field = QPushButton(tr("vector.add_field"))
        self._btn_add_field.clicked.connect(self._on_add_field)
        self._btn_mod_field = QPushButton(tr("vector.modify_field"))
        self._btn_mod_field.clicked.connect(self._on_modify_field)
        self._btn_del_field = QPushButton(tr("vector.delete_field"))
        self._btn_del_field.clicked.connect(self._on_delete_field)
        prop_btn_row.addWidget(self._btn_add_field)
        prop_btn_row.addWidget(self._btn_mod_field)
        prop_btn_row.addWidget(self._btn_del_field)
        layout.addLayout(prop_btn_row)

        return group

    # ======================================================================
    # Dataset / feature helpers
    # ======================================================================

    def _find_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        for ds in self._datasets:
            if ds.get("id") == dataset_id:
                return ds
        return None

    def _find_feature(self, dataset_id: str, feature_id: str) -> dict[str, Any] | None:
        ds = self._find_dataset(dataset_id)
        if ds is None:
            return None
        for f in ds.get("features", []):
            if f.get("id") == feature_id:
                return f
        return None

    def _find_feature_owner(self, feature_id: str) -> str | None:
        return self._feature_owners.get(feature_id)

    def _active_dataset(self) -> dict[str, Any] | None:
        if self._active_dataset_id:
            return self._find_dataset(self._active_dataset_id)
        # fall back to first visible dataset
        for ds in self._datasets:
            if ds.get("visible", True):
                return ds
        if self._datasets:
            return self._datasets[0]
        return None

    def _all_features(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for ds in self._datasets:
            if ds.get("visible", True):
                result.extend(ds.get("features", []))
        return result

    # ======================================================================
    # Geometry helpers
    # ======================================================================

    @staticmethod
    def _geom_type_from_feature(feature: dict[str, Any]) -> GeometryType:
        """Best-effort extraction of geometry type from a dict feature."""
        geom = feature.get("geometry", {})
        if isinstance(geom, dict):
            gt = geom.get("type", "Point")
        else:
            gt = "Point"
        try:
            return GeometryType(str(gt))
        except ValueError:
            return GeometryType.POINT

    @staticmethod
    def _extract_coords(feature: dict[str, Any]) -> list[tuple[float, float]]:
        """Return a flat list of (x, y) coordinate pairs for a feature."""
        geom = feature.get("geometry", {})
        if not isinstance(geom, dict):
            return []
        coords = geom.get("coordinates", [])
        gt = geom.get("type", "Point")

        if gt == "Point":
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                return [(float(coords[0]), float(coords[1]))]
            return []
        elif gt in ("LineString", "MultiPoint"):
            if isinstance(coords, list):
                return [(float(pt[0]), float(pt[1])) for pt in coords if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            return []
        elif gt == "Polygon":
            # Outer ring only
            if isinstance(coords, list) and len(coords) > 0:
                ring = coords[0]
                if isinstance(ring, list):
                    return [(float(pt[0]), float(pt[1])) for pt in ring if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            return []
        else:
            return []

    def _translate_feature_geometry(self, feature: dict[str, Any], dx: float, dy: float) -> None:
        """Translate all coordinates of a feature in-place."""
        geom = feature.get("geometry", {})
        if not isinstance(geom, dict):
            return
        coords = geom.get("coordinates")
        if coords is None:
            return
        gt = geom.get("type", "Point")

        def _shift(pt):
            return [pt[0] + dx, pt[1] + dy]

        if gt == "Point":
            if isinstance(coords, list) and len(coords) >= 2:
                geom["coordinates"] = _shift(coords)
        elif gt in ("LineString", "MultiPoint"):
            if isinstance(coords, list):
                geom["coordinates"] = [_shift(pt) for pt in coords]
        elif gt == "Polygon":
            if isinstance(coords, list):
                geom["coordinates"] = [[_shift(pt) for pt in ring] for ring in coords]
        elif gt == "MultiLineString":
            if isinstance(coords, list):
                geom["coordinates"] = [[_shift(pt) for pt in line] for line in coords]
        elif gt == "MultiPolygon":
            if isinstance(coords, list):
                geom["coordinates"] = [
                    [[_shift(pt) for pt in ring] for ring in poly]
                    for poly in coords
                ]

    @staticmethod
    def _set_vertex(feature: dict[str, Any], index: int, new_pt: tuple[float, float]) -> None:
        """Set a single vertex coordinate. Handles point, line, and polygon."""
        geom = feature.get("geometry", {})
        if not isinstance(geom, dict):
            return
        coords = geom.get("coordinates")
        gt = geom.get("type", "Point")
        x, y = float(new_pt[0]), float(new_pt[1])

        if gt == "Point":
            geom["coordinates"] = [x, y]
        elif gt == "LineString":
            if isinstance(coords, list) and 0 <= index < len(coords):
                coords[index] = [x, y]
        elif gt == "Polygon":
            if isinstance(coords, list) and len(coords) > 0:
                ring = coords[0]
                if isinstance(ring, list) and 0 <= index < len(ring):
                    ring[index] = [x, y]

    @staticmethod
    def _distance(pt1: tuple[float, float], pt2: tuple[float, float]) -> float:
        return ((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2) ** 0.5

    @staticmethod
    def _snapshot_geometry_coords(feature: dict[str, Any]) -> list[tuple[float, float]]:
        """Deep-copy the geometry coordinates for move-undo snapshots."""
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates") if isinstance(geom, dict) else None

        def _deep_copy(obj):
            if isinstance(obj, list):
                return [_deep_copy(v) for v in obj]
            if isinstance(obj, (int, float)):
                return float(obj)
            return obj

        return _deep_copy(coords) if coords is not None else []

    def _restore_geometry_from_snapshot(self, feature: dict[str, Any],
                                         snapshot: list[tuple[float, float]] | list) -> None:
        """Restore a feature's geometry coordinates from a snapshot."""
        geom = feature.get("geometry", {})
        if not isinstance(geom, dict):
            return

        def _deep_copy(obj):
            if isinstance(obj, list):
                return [_deep_copy(v) for v in obj]
            if isinstance(obj, (int, float)):
                return float(obj)
            return obj

        geom["coordinates"] = _deep_copy(snapshot)

    # ======================================================================
    # Rendering – rebuild all vector overlays
    # ======================================================================

    def _rebuild_overlays(self) -> None:
        """Clear and re-create all QGraphicsItems for current datasets."""
        self._viewer.clear_overlays()
        self._layer_groups.clear()

        # Re-create per-dataset groups
        for ds in self._datasets:
            if not ds.get("visible", True):
                continue
            group = QGraphicsItemGroup()
            self._viewer.scene().addItem(group)
            ds_c = self._dataset_color(ds)
            self._layer_groups[ds["id"]] = group

            for feature in ds.get("features", []):
                self._render_feature(feature, group, ds_c)

        # Re-apply highlight
        self._clear_highlight()
        if self._selected_feature_id is not None:
            self._highlight_feature(self._selected_feature_id)

    def _render_feature(self, feature: dict[str, Any],
                        group: QGraphicsItemGroup, color: QColor) -> None:
        """Add QGraphicsItems for a single feature to the target group."""
        geom_type = self._geom_type_from_feature(feature)
        coords = self._extract_coords(feature)
        pen = QPen(color, LINE_WIDTH)
        brush = QBrush(color)

        scene = self._viewer.scene()

        if geom_type == GeometryType.POINT:
            for x, y in coords:
                item = scene.addEllipse(
                    x - POINT_RADIUS, y - POINT_RADIUS,
                    POINT_RADIUS * 2, POINT_RADIUS * 2,
                    pen, brush,
                )
                item.setData(0, feature.get("id"))
                item.setParentItem(group)

        elif geom_type == GeometryType.LINE_STRING:
            if len(coords) >= 2:
                poly = QPolygonF([QPointF(x, y) for x, y in coords])
                item = QGraphicsPolygonItem()
                item.setPolygon(poly)
                item.setPen(pen)
                item.setBrush(Qt.BrushStyle.NoBrush)
                item.setData(0, feature.get("id"))
                scene.addItem(item)
                item.setParentItem(group)

        elif geom_type == GeometryType.POLYGON:
            if len(coords) >= 3:
                poly = QPolygonF([QPointF(x, y) for x, y in coords])
                item = QGraphicsPolygonItem()
                item.setPolygon(poly)
                item.setPen(pen)
                fill_color = QColor(color)
                fill_color.setAlpha(40)
                item.setBrush(QBrush(fill_color))
                item.setData(0, feature.get("id"))
                scene.addItem(item)
                item.setParentItem(group)

        elif geom_type in (GeometryType.MULTI_POINT,
                           GeometryType.MULTI_LINE_STRING,
                           GeometryType.MULTI_POLYGON):
            # Fallback: render each coordinate ring separately
            # For multi-geometries the coordinates are nested arrays
            geom = feature.get("geometry", {})
            raw = geom.get("coordinates", []) if isinstance(geom, dict) else []
            if geom_type == GeometryType.MULTI_POINT:
                if isinstance(raw, list):
                    for sub in raw:
                        if isinstance(sub, (list, tuple)) and len(sub) >= 2:
                            item = scene.addEllipse(
                                sub[0] - POINT_RADIUS, sub[1] - POINT_RADIUS,
                                POINT_RADIUS * 2, POINT_RADIUS * 2,
                                pen, brush,
                            )
                            item.setData(0, feature.get("id"))
                            item.setParentItem(group)
            elif isinstance(raw, list):
                for sub in raw:
                    if isinstance(sub, list) and len(sub) >= 2:
                        pts = [(float(pt[0]), float(pt[1])) for pt in sub
                               if isinstance(pt, (list, tuple)) and len(pt) >= 2]
                        if len(pts) < 2:
                            continue
                        poly = QPolygonF([QPointF(x, y) for x, y in pts])
                        item = QGraphicsPolygonItem()
                        item.setPolygon(poly)
                        item.setPen(pen)
                        if geom_type == GeometryType.MULTI_POLYGON:
                            fc = QColor(color)
                            fc.setAlpha(40)
                            item.setBrush(QBrush(fc))
                        else:
                            item.setBrush(Qt.BrushStyle.NoBrush)
                        item.setData(0, feature.get("id"))
                        scene.addItem(item)
                        item.setParentItem(group)

    def _dataset_color(self, ds: dict[str, Any]) -> QColor:
        """Return a display color for this dataset based on its geometry type."""
        gt_str = ds.get("geom_type", "Point")
        try:
            gt = GeometryType(gt_str)
        except ValueError:
            gt = GeometryType.POINT
        return TYPE_COLORS.get(gt, QColor(200, 200, 200))

    # ======================================================================
    # Highlight / selection
    # ======================================================================

    def _clear_highlight(self) -> None:
        """Remove all highlight overlays."""
        scene = self._viewer.scene()
        for item in self._highlight_items:
            scene.removeItem(item)
        self._highlight_items.clear()

    def _highlight_feature(self, feature_id: str) -> None:
        """Draw selection highlight + vertex handles for a feature."""
        owner_id = self._feature_owners.get(feature_id)
        if owner_id is None:
            return
        feat = self._find_feature(owner_id, feature_id)
        if feat is None:
            return
        coords = self._extract_coords(feat)
        if not coords:
            return

        scene = self._viewer.scene()
        geom_type = self._geom_type_from_feature(feat)

        # Bounding rect highlight
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        if xs and ys:
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            margin = 6
            rect = QGraphicsRectItem(
                x1 - margin, y1 - margin - 0,
                max(x2 - x1 + 2 * margin, 1),
                max(y2 - y1 + 2 * margin, 1),
            )
            rect.setPen(QPen(HIGHLIGHT_COLOR, 2, Qt.PenStyle.DashLine))
            rect.setBrush(Qt.BrushStyle.NoBrush)
            rect.setZValue(100)
            scene.addItem(rect)
            self._highlight_items.append(rect)

        # Vertex handles
        if geom_type in (GeometryType.POINT, GeometryType.LINE_STRING,
                         GeometryType.POLYGON):
            for i, (x, y) in enumerate(coords):
                handle = scene.addEllipse(
                    x - VERTEX_RADIUS, y - VERTEX_RADIUS,
                    VERTEX_RADIUS * 2, VERTEX_RADIUS * 2,
                    QPen(VERTEX_COLOR, 1.5),
                    QBrush(VERTEX_COLOR),
                )
                handle.setZValue(101)
                handle.setData(0, f"vertex:{feature_id}:{i}")
                self._highlight_items.append(handle)

    def _select_feature(self, feature_id: str | None) -> None:
        """Set the selected feature, update highlights and property editor."""
        self._clear_highlight()
        self._selected_feature_id = feature_id
        if feature_id is not None:
            self._highlight_feature(feature_id)
        self._refresh_property_editor()

    # ======================================================================
    # Layer tree
    # ======================================================================

    def _refresh_layer_tree(self) -> None:
        """Rebuild the layer QTreeWidget from self._datasets."""
        self._layer_tree.blockSignals(True)
        self._layer_tree.clear()

        for ds in self._datasets:
            item = QTreeWidgetItem()
            item.setText(0, ds.get("name", tr("vector.name_unnamed")))
            item.setText(1, str(len(ds.get("features", []))))
            item.setData(0, Qt.ItemDataRole.UserRole, ds.get("id"))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if ds.get("visible", True)
                               else Qt.CheckState.Unchecked)
            self._layer_tree.addTopLevelItem(item)

        self._layer_tree.blockSignals(False)

    def _on_layer_visibility_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        ds_id = item.data(0, Qt.ItemDataRole.UserRole)
        ds = self._find_dataset(ds_id)
        if ds is None:
            return
        visible = item.checkState(0) == Qt.CheckState.Checked
        ds["visible"] = visible
        self._rebuild_overlays()

    def _on_layer_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        ds_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._active_dataset_id = ds_id

    def _on_layer_context_menu(self, pos) -> None:
        item = self._layer_tree.itemAt(pos)
        if item is None:
            return
        ds_id = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        action_del = menu.addAction(tr("vector.context_delete_layer"))
        action = menu.exec(self._layer_tree.viewport().mapToGlobal(pos))
        if action == action_del:
            self._delete_dataset(ds_id)

    def _on_delete_layer(self) -> None:
        selected = self._layer_tree.currentItem()
        if selected is None:
            return
        ds_id = selected.data(0, Qt.ItemDataRole.UserRole)
        self._delete_dataset(ds_id)

    def _delete_dataset(self, ds_id: str) -> None:
        ds = self._find_dataset(ds_id)
        if ds is None:
            return
        name = ds.get("name", tr("vector.name_unnamed"))
        reply = QMessageBox.question(
            self, tr("vector.dialog_delete_title"),
            tr("vector.dialog_delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Remove feature ownership tracking
        for f in ds.get("features", []):
            fid = f.get("id")
            if fid:
                self._feature_owners.pop(fid, None)
                if self._selected_feature_id == fid:
                    self._selected_feature_id = None
        self._datasets = [d for d in self._datasets if d.get("id") != ds_id]
        if self._active_dataset_id == ds_id:
            self._active_dataset_id = None
        self._rebuild_overlays()
        self._refresh_layer_tree()
        self._refresh_property_editor()

    # ======================================================================
    # Property editor
    # ======================================================================

    def _refresh_property_editor(self) -> None:
        self._property_table.blockSignals(True)
        self._property_table.setRowCount(0)

        if self._selected_feature_id is None:
            self._property_label.setText(tr("vector.no_feature_selected"))
            self._property_table.blockSignals(False)
            return

        owner_id = self._feature_owners.get(self._selected_feature_id)
        feat = self._find_feature(owner_id, self._selected_feature_id) if owner_id else None
        if feat is None:
            self._property_label.setText(tr("vector.no_feature_selected"))
            self._property_table.blockSignals(False)
            return

        geom_type = self._geom_type_from_feature(feat)
        self._property_label.setText(
            f"Feature: {self._selected_feature_id[:8]}...  "
            f"Type: {geom_type.value}"
        )

        props = feat.get("properties", {})
        sorted_keys = sorted(props.keys())
        self._property_table.setRowCount(len(sorted_keys))
        for row, key in enumerate(sorted_keys):
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._property_table.setItem(row, 0, key_item)
            val_item = QTableWidgetItem(str(props[key]) if props[key] is not None else "")
            self._property_table.setItem(row, 1, val_item)

        self._property_table.blockSignals(False)

    def _on_property_cell_changed(self, row: int, column: int) -> None:
        if column != 1:
            return
        if self._selected_feature_id is None:
            return
        key_item = self._property_table.item(row, 0)
        val_item = self._property_table.item(row, 1)
        if key_item is None or val_item is None:
            return
        field = key_item.text()
        new_value = val_item.text()

        owner_id = self._feature_owners.get(self._selected_feature_id)
        if owner_id is None:
            return
        feat = self._find_feature(owner_id, self._selected_feature_id)
        if feat is None:
            return

        props = feat.get("properties", {})
        old_value = props.get(field, "")

        if str(old_value) == new_value:
            return

        cmd = _UpdatePropertyCommand(owner_id, self._selected_feature_id,
                                     field, old_value, new_value)
        cmd.do(self)
        self._push_command(cmd)

    def _on_add_field(self) -> None:
        if self._selected_feature_id is None:
            notify(self, tr("vector.warn_select_feature"), "warning")
            return
        field_name, ok = QInputDialog.getText(self, tr("vector.dialog_add_field"), tr("vector.dialog_field_name"))
        if not ok or not field_name.strip():
            return
        owner_id = self._feature_owners.get(self._selected_feature_id)
        if owner_id is None:
            return
        feat = self._find_feature(owner_id, self._selected_feature_id)
        if feat is None:
            return
        props = feat.get("properties", {})
        if field_name.strip() in props:
            notify(self, tr("vector.warn_field_exists", name=field_name), "warning")
            return
        props[field_name.strip()] = ""
        self._rebuild_overlays()
        self._refresh_property_editor()
        mark_project_dirty(self.window())

    def _on_modify_field(self) -> None:
        selected_row = self._property_table.currentRow()
        if selected_row < 0:
            notify(self, tr("vector.warn_select_field"), "warning")
            return
        key_item = self._property_table.item(selected_row, 0)
        if key_item is None:
            return
        old_name = key_item.text()
        new_name, ok = QInputDialog.getText(
            self, tr("vector.dialog_rename_field"), tr("vector.dialog_new_field_name"), text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if self._selected_feature_id is None:
            return
        owner_id = self._feature_owners.get(self._selected_feature_id)
        if owner_id is None:
            return
        feat = self._find_feature(owner_id, self._selected_feature_id)
        if feat is None:
            return
        props = feat.get("properties", {})
        if new_name.strip() in props:
            notify(self, tr("vector.warn_field_exists", name=new_name), "warning")
            return
        value = props.pop(old_name, "")
        props[new_name.strip()] = value
        self._refresh_property_editor()
        mark_project_dirty(self.window())

    def _on_delete_field(self) -> None:
        selected_row = self._property_table.currentRow()
        if selected_row < 0:
            notify(self, tr("vector.warn_select_field"), "warning")
            return
        key_item = self._property_table.item(selected_row, 0)
        if key_item is None:
            return
        field = key_item.text()
        if self._selected_feature_id is None:
            return
        owner_id = self._feature_owners.get(self._selected_feature_id)
        if owner_id is None:
            return
        feat = self._find_feature(owner_id, self._selected_feature_id)
        if feat is None:
            return
        props = feat.get("properties", {})
        if field in props:
            del props[field]
        self._refresh_property_editor()
        mark_project_dirty(self.window())

    # ======================================================================
    # Mouse interaction on viewer
    # ======================================================================

    def _get_scene_pos(self, event) -> tuple[float, float]:
        """Convert a QMouseEvent position to scene coordinates."""
        pt = self._viewer.mapToScene(int(event.position().x()),
                                      int(event.position().y()))
        return (pt.x(), pt.y())

    def _on_viewer_mouse_press(self, event) -> None:
        """Handle mouse press based on current edit mode."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_left_press(self._get_scene_pos(event))
        elif event.button() == Qt.MouseButton.RightButton:
            self._handle_right_press(self._get_scene_pos(event))
        else:
            # Still allow base viewer pan behavior for middle button
            RasterViewer.mousePressEvent(self._viewer, event)

    def _on_viewer_mouse_move(self, event) -> None:
        """Handle mouse move – rubber-band drawing, vertex drag, feature move."""
        pt = self._get_scene_pos(event)
        self._last_mouse_pos = pt

        if self._mode == EditMode.DRAW_LINE or self._mode == EditMode.DRAW_POLYGON:
            if self._draw_points:
                self._update_rubber_band(pt)

        elif self._mode == EditMode.EDIT_VERTICES:
            if self._editing_vertex_feature is not None and self._vertex_drag_start is not None:
                # Drag vertex
                feat = self._find_feature(self._editing_vertex_dataset,
                                          self._editing_vertex_feature)
                if feat is not None:
                    self._set_vertex(feat, self._editing_vertex_index, pt)
                    self._rebuild_overlays()
                    self._highlight_feature(self._editing_vertex_feature)

        elif self._mode == EditMode.MOVE:
            if (self._move_start is not None and self._move_start_feat_pos is not None
                    and self._selected_feature_id is not None):
                owner_id = self._feature_owners.get(self._selected_feature_id)
                feat = self._find_feature(owner_id, self._selected_feature_id) if owner_id else None
                if feat is not None and self._move_snapshot_coords is not None:
                    # Reset geometry to snapshot, then apply full delta from drag origin
                    self._restore_geometry_from_snapshot(
                        feat, self._move_snapshot_coords
                    )
                    dx = pt[0] - self._move_start_feat_pos[0]
                    dy = pt[1] - self._move_start_feat_pos[1]
                    self._translate_feature_geometry(feat, dx, dy)
                    self._rebuild_overlays()
                    self._highlight_feature(self._selected_feature_id)

        # Emit cursor move for coordinates display
        px, py = int(pt[0]), int(pt[1])
        gx, gy = self._viewer.pixel_to_geo(px, py)
        self._viewer.cursorMoved.emit(px, py, gx, gy)

    def _on_viewer_mouse_release(self, event) -> None:
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            pt = self._get_scene_pos(event)

            if self._mode == EditMode.MOVE:
                if (self._move_start is not None and self._selected_feature_id is not None):
                    owner_id = self._feature_owners.get(self._selected_feature_id)
                    total_dx = pt[0] - self._move_start_feat_pos[0]
                    total_dy = pt[1] - self._move_start_feat_pos[1]
                    if abs(total_dx) > 0.5 or abs(total_dy) > 0.5 and owner_id:
                        cmd = _MoveFeatureCommand(
                            owner_id, self._selected_feature_id, total_dx, total_dy
                        )
                        self._push_command(cmd)
                self._move_start = None
                self._move_start_feat_pos = None
                self._move_snapshot_coords = None

            elif self._mode == EditMode.EDIT_VERTICES:
                if (self._vertex_drag_start is not None
                        and self._editing_vertex_feature is not None
                        and self._editing_vertex_dataset is not None):
                    old_pt = self._vertex_drag_start
                    new_pt = pt
                    if self._distance(old_pt, new_pt) > 0.5:
                        cmd = _MoveVertexCommand(
                            self._editing_vertex_dataset,
                            self._editing_vertex_feature,
                            self._editing_vertex_index,
                            old_pt, new_pt,
                        )
                        self._push_command(cmd)
                self._vertex_drag_start = None
                self._editing_vertex_dataset = None
                self._editing_vertex_feature = None
                self._editing_vertex_index = -1

        # Middle-button: fall through to RasterViewer for pan
        elif event.button() == Qt.MouseButton.MiddleButton:
            RasterViewer.mouseReleaseEvent(self._viewer, event)

    def _on_viewer_double_click(self, event) -> None:
        """Double-click / right-click finish drawing."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._finish_drawing()

    def _on_viewer_context_menu(self, pos) -> None:
        """Right-click context menu or finish drawing."""
        scene_pt = self._viewer.mapToScene(pos)
        pt = (scene_pt.x(), scene_pt.y())

        if self._mode in (EditMode.DRAW_LINE, EditMode.DRAW_POLYGON):
            self._finish_drawing()
        else:
            # Default context menu
            menu = QMenu(self)
            menu.addAction(tr("vector.context_fit_view"), self._viewer.fit_to_view)
            menu.addAction(tr("vector.context_zoom_actual"), self._viewer.zoom_actual)
            menu.exec(self._viewer.viewport().mapToGlobal(pos))

    # ----- press handlers ------------------------------------------------

    def _handle_left_press(self, pt: tuple[float, float]) -> None:
        if self._mode == EditMode.SELECT:
            self._do_select(pt)
        elif self._mode == EditMode.DRAW_POINT:
            self._do_draw_point(pt)
        elif self._mode == EditMode.DRAW_LINE:
            self._do_add_draw_vertex(pt)
        elif self._mode == EditMode.DRAW_POLYGON:
            self._do_add_draw_vertex(pt)
        elif self._mode == EditMode.EDIT_VERTICES:
            self._do_vertex_grab(pt)
        elif self._mode == EditMode.MOVE:
            self._do_move_start(pt)

    def _handle_right_press(self, pt: tuple[float, float]) -> None:
        if self._mode in (EditMode.DRAW_LINE, EditMode.DRAW_POLYGON):
            self._finish_drawing()

    # ----- select ---------------------------------------------------------

    def _do_select(self, pt: tuple[float, float]) -> None:
        """Click to select the nearest feature within SELECT_TOLERANCE."""
        best_id: str | None = None
        best_dist = float("inf")

        for ds in self._datasets:
            if not ds.get("visible", True):
                continue
            for feat in ds.get("features", []):
                coords = self._extract_coords(feat)
                if not coords:
                    continue
                geom_type = self._geom_type_from_feature(feat)
                d = self._point_to_geometry_distance(pt, coords, geom_type)
                if d < best_dist:
                    best_dist = d
                    best_id = feat.get("id")

        if best_id is not None and best_dist <= SELECT_TOLERANCE:
            self._select_feature(best_id)
        else:
            self._select_feature(None)

    def _point_to_geometry_distance(self, pt: tuple[float, float],
                                    coords: list[tuple[float, float]],
                                    geom_type: GeometryType) -> float:
        """Minimum distance from pt to a geometry (in pixels)."""
        if geom_type == GeometryType.POINT:
            return min(self._distance(pt, c) for c in coords) if coords else float("inf")
        elif geom_type == GeometryType.LINE_STRING:
            return self._point_to_polyline_distance(pt, coords)
        elif geom_type == GeometryType.POLYGON:
            # Distance to boundary + check if point is inside
            d = self._point_to_polyline_distance(pt, coords, closed=True)
            if self._point_in_polygon(pt, coords):
                return 0.0
            return d
        return float("inf")

    @staticmethod
    def _point_to_polyline_distance(pt: tuple[float, float],
                                    coords: list[tuple[float, float]],
                                    closed: bool = False) -> float:
        """Minimum distance from a point to a polyline."""
        if len(coords) < 2:
            return (VectorTab._distance(pt, coords[0]) if coords
                    else float("inf"))
        best = float("inf")
        n = len(coords)
        for i in range(n - 1):
            d = VectorTab._point_to_segment_distance(pt, coords[i], coords[i + 1])
            if d < best:
                best = d
        if closed and len(coords) >= 2:
            d = VectorTab._point_to_segment_distance(pt, coords[-1], coords[0])
            if d < best:
                best = d
        return best

    @staticmethod
    def _point_to_segment_distance(pt: tuple[float, float],
                                   a: tuple[float, float],
                                   b: tuple[float, float]) -> float:
        """Shortest distance from pt to line segment ab."""
        ax, ay = a
        bx, by = b
        px, py = pt

        abx = bx - ax
        aby = by - ay
        if abx == 0 and aby == 0:
            return VectorTab._distance(pt, a)

        t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)))
        near_x = ax + t * abx
        near_y = ay + t * aby
        return VectorTab._distance(pt, (near_x, near_y))

    @staticmethod
    def _point_in_polygon(pt: tuple[float, float],
                          coords: list[tuple[float, float]]) -> bool:
        """Ray-casting point-in-polygon test."""
        x, y = pt
        inside = False
        n = len(coords)
        j = n - 1
        for i in range(n):
            xi, yi = coords[i]
            xj, yj = coords[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    # ----- draw point -----------------------------------------------------

    def _do_draw_point(self, pt: tuple[float, float]) -> None:
        """Add a point feature at the clicked location."""
        ds = self._active_dataset()
        if ds is None:
            notify(self, tr("vector.warn_no_active_layer"), "warning")
            return
        feature = {
            "id": str(uuid.uuid4()),
            "geometry": {"type": "Point", "coordinates": [pt[0], pt[1]]},
            "properties": {},
        }
        cmd = _AddFeatureCommand(ds["id"], feature)
        cmd.do(self)
        self._push_command(cmd)

    # ----- draw line / polygon (vertex accumulation) -----------------------

    def _do_add_draw_vertex(self, pt: tuple[float, float]) -> None:
        self._draw_points.append(pt)
        self._update_rubber_band(self._last_mouse_pos or pt)

    def _update_rubber_band(self, current_pt: tuple[float, float]) -> None:
        """Draw or update the rubber-band preview during line/polygon drawing."""
        self._clear_rubber_band()
        if not self._draw_points:
            return

        scene = self._viewer.scene()

        # Draw committed vertices as small circles
        for x, y in self._draw_points:
            item = scene.addEllipse(
                x - VERTEX_RADIUS, y - VERTEX_RADIUS,
                VERTEX_RADIUS * 2, VERTEX_RADIUS * 2,
                QPen(QColor(255, 255, 0)), QBrush(QColor(255, 255, 0)),
            )
            item.setZValue(200)
            self._highlight_items.append(item)

        # Draw the connecting lines
        all_pts = list(self._draw_points) + [current_pt]
        if len(all_pts) >= 2:
            for i in range(len(all_pts) - 1):
                x1, y1 = all_pts[i]
                x2, y2 = all_pts[i + 1]
                pen = QPen(QColor(255, 255, 0), LINE_WIDTH, Qt.PenStyle.DashLine)
                line = scene.addLine(x1, y1, x2, y2, pen)
                line.setZValue(199)
                self._highlight_items.append(line)

        # For polygon, show the closing line
        if (self._mode == EditMode.DRAW_POLYGON
                and len(self._draw_points) >= 2):
            x1, y1 = current_pt
            x2, y2 = self._draw_points[0]
            pen = QPen(QColor(255, 255, 0, 100), LINE_WIDTH, Qt.PenStyle.DotLine)
            line = scene.addLine(x1, y1, x2, y2, pen)
            line.setZValue(198)
            self._highlight_items.append(line)

    def _clear_rubber_band(self) -> None:
        scene = self._viewer.scene()
        for item in self._highlight_items:
            scene.removeItem(item)
        self._highlight_items.clear()

    def _finish_drawing(self) -> None:
        """Complete the current line or polygon drawing."""
        if self._mode not in (EditMode.DRAW_LINE, EditMode.DRAW_POLYGON):
            return
        if not self._draw_points:
            return

        ds = self._active_dataset()
        if ds is None:
            self._draw_points.clear()
            self._clear_rubber_band()
            notify(self, tr("vector.warn_no_active_layer"), "warning")
            return

        if self._mode == EditMode.DRAW_LINE:
            if len(self._draw_points) < 2:
                notify(self, tr("vector.warn_line_vertices"), "warning")
                self._draw_points.clear()
                self._clear_rubber_band()
                return
            feature = {
                "id": str(uuid.uuid4()),
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[pt[0], pt[1]] for pt in self._draw_points],
                },
                "properties": {},
            }
        else:  # DRAW_POLYGON
            if len(self._draw_points) < 3:
                notify(self, tr("vector.warn_polygon_vertices"), "warning")
                self._draw_points.clear()
                self._clear_rubber_band()
                return
            feature = {
                "id": str(uuid.uuid4()),
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[pt[0], pt[1]] for pt in self._draw_points]],
                },
                "properties": {},
            }

        cmd = _AddFeatureCommand(ds["id"], feature)
        cmd.do(self)
        self._push_command(cmd)

        self._draw_points.clear()
        self._clear_rubber_band()

    # ----- edit vertices --------------------------------------------------

    def _do_vertex_grab(self, pt: tuple[float, float]) -> None:
        """Find nearest vertex and start dragging it."""
        best_ds_id: str | None = None
        best_feat_id: str | None = None
        best_idx: int = -1
        best_dist: float = float("inf")

        for ds in self._datasets:
            if not ds.get("visible", True):
                continue
            for feat in ds.get("features", []):
                coords = self._extract_coords(feat)
                for i, c in enumerate(coords):
                    d = self._distance(pt, c)
                    if d < best_dist:
                        best_dist = d
                        best_ds_id = ds["id"]
                        best_feat_id = feat.get("id")
                        best_idx = i

        if best_feat_id is not None and best_dist <= SELECT_TOLERANCE * 2:
            self._editing_vertex_dataset = best_ds_id
            self._editing_vertex_feature = best_feat_id
            self._editing_vertex_index = best_idx
            feat = self._find_feature(best_ds_id, best_feat_id)
            coords = self._extract_coords(feat) if feat else []
            if best_idx < len(coords):
                self._vertex_drag_start = coords[best_idx]
            else:
                self._vertex_drag_start = pt
            self._select_feature(best_feat_id)
        else:
            self._editing_vertex_dataset = None
            self._editing_vertex_feature = None
            self._editing_vertex_index = -1
            self._vertex_drag_start = None

    # ----- move -----------------------------------------------------------

    def _do_move_start(self, pt: tuple[float, float]) -> None:
        """Start dragging the selected feature, or select one under cursor."""
        if self._selected_feature_id is not None:
            # Check if cursor is near the selected feature
            owner_id = self._feature_owners.get(self._selected_feature_id)
            feat = self._find_feature(owner_id, self._selected_feature_id) if owner_id else None
            if feat is not None:
                coords = self._extract_coords(feat)
                gt = self._geom_type_from_feature(feat)
                d = self._point_to_geometry_distance(pt, coords, gt)
                if d <= SELECT_TOLERANCE * 3:
                    self._move_start = pt
                    self._move_snapshot_coords = self._snapshot_geometry_coords(feat)
                    if coords:
                        self._move_start_feat_pos = coords[0]
                    else:
                        self._move_start_feat_pos = pt
                    return

        # Try to select and move
        self._do_select(pt)
        if self._selected_feature_id is not None:
            self._move_start = pt
            owner_id = self._feature_owners.get(self._selected_feature_id)
            feat = self._find_feature(owner_id, self._selected_feature_id) if owner_id else None
            coords = self._extract_coords(feat) if feat else []
            self._move_start_feat_pos = coords[0] if coords else pt
            self._move_snapshot_coords = self._snapshot_geometry_coords(feat) if feat else None

    # ======================================================================
    # Undo / Redo
    # ======================================================================

    def _push_command(self, cmd: _Command) -> None:
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        mark_project_dirty(self.window())

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        cmd = self._undo_stack.pop()
        cmd.undo(self)
        self._redo_stack.append(cmd)

    def _redo(self) -> None:
        if not self._redo_stack:
            return
        cmd = self._redo_stack.pop()
        cmd.do(self)
        self._undo_stack.append(cmd)

    # ======================================================================
    # Tool change
    # ======================================================================

    def _on_tool_changed(self, button, checked: bool) -> None:
        if not checked:
            return
        obj_name = button.objectName()
        new_mode = BUTTON_MODE_MAP.get(obj_name, EditMode.SELECT)

        # Finish any pending drawing before switching
        if self._mode in (EditMode.DRAW_LINE, EditMode.DRAW_POLYGON):
            self._finish_drawing()

        self._mode = new_mode
        self._draw_points.clear()
        self._clear_rubber_band()
        self._move_start = None
        self._move_start_feat_pos = None
        self._move_snapshot_coords = None
        self._editing_vertex_dataset = None
        self._editing_vertex_feature = None
        self._editing_vertex_index = -1
        self._vertex_drag_start = None

        # Update cursor
        if self._mode in (EditMode.DRAW_POINT, EditMode.DRAW_LINE,
                          EditMode.DRAW_POLYGON):
            self._viewer.setCursor(Qt.CursorShape.CrossCursor)
        elif self._mode == EditMode.MOVE:
            self._viewer.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._mode == EditMode.EDIT_VERTICES:
            self._viewer.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._viewer.setCursor(Qt.CursorShape.ArrowCursor)

    # ======================================================================
    # File operations
    # ======================================================================

    def _on_load_vector(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("vector.dialog_load_vector"), "",
            tr("vector.filter_vector")
        )
        if not path:
            return
        self._load_vector_path(path)

    def _on_load_base_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("vector.dialog_load_base_image"), "",
            tr("vector.filter_image")
        )
        if not path:
            return
        self._base_image_path = path
        self._viewer.load(path)
        notify(self, tr("vector.info_base_loaded", name=path.split('/')[-1]), "info")

    def _load_vector_path(self, path: str) -> None:
        """Load a vector file via VectorService and add as a new dataset."""
        if self._ctx is None:
            notify(self, tr("vector.err_no_context"), "error")
            return

        data = self._ctx.vector_service.read(path)
        if data is None:
            notify(self, tr("vector.err_load_failed", path=path), "error")
            return

        from pathlib import Path
        name = Path(path).stem

        # Normalize the data dict structure
        features = data.get("features", [])
        if not features and "geometries" in data:
            features = data["geometries"]

        # Ensure each feature has an id
        for f in features:
            if not f.get("id"):
                f["id"] = str(uuid.uuid4())

        geom_type = data.get("geometry_type") or data.get("type", "Point")

        dataset = {
            "id": str(uuid.uuid4()),
            "name": name,
            "path": str(path),
            "geom_type": geom_type,
            "features": features,
            "visible": True,
        }

        for f in features:
            self._feature_owners[f["id"]] = dataset["id"]

        self._datasets.append(dataset)
        self._active_dataset_id = dataset["id"]

        self._rebuild_overlays()
        self._refresh_layer_tree()
        self._refresh_property_editor()
        notify(self, tr("vector.info_loaded", count=len(features), name=name), "info")
        mark_project_dirty(self.window())

    def _on_new_layer(self) -> None:
        """Create a new empty layer."""
        name, ok = QInputDialog.getText(self, tr("vector.dialog_new_layer"), tr("vector.dialog_layer_name"))
        if not ok or not name.strip():
            return

        from PySide6.QtWidgets import QInputDialog as QID
        geom_types = ["Point", "LineString", "Polygon"]
        gt, ok2 = QID.getItem(self, tr("vector.dialog_geom_type_title"), tr("vector.dialog_geom_type"),
                              geom_types, 0, False)
        if not ok2:
            return

        if self._ctx is not None:
            layer_data = self._ctx.vector_service.create_layer(name.strip(), gt)
        else:
            layer_data = {"type": gt, "features": [], "geometry_type": gt}

        dataset = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "path": "",
            "geom_type": gt,
            "features": layer_data.get("features", []),
            "visible": True,
        }

        self._datasets.append(dataset)
        self._active_dataset_id = dataset["id"]

        self._rebuild_overlays()
        self._refresh_layer_tree()
        self._refresh_property_editor()
        notify(self, tr("vector.info_layer_created", name=name.strip(), gt=gt), "info")
        mark_project_dirty(self.window())

    def _on_export(self, fmt: str) -> None:
        """Export the active dataset to the selected format."""
        ds = self._active_dataset()
        if ds is None:
            notify(self, tr("vector.warn_no_export_layer"), "warning")
            return

        ext_map = {"shp": ".shp", "geojson": ".geojson", "dxf": ".dxf"}
        ext = ext_map.get(fmt, ".shp")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("vector.dialog_export_title", fmt=fmt.upper()),
            ds.get("name", "export") + ext,
            f"{fmt.upper()} Files (*{ext})"
        )
        if not path:
            return

        if self._ctx is None:
            notify(self, tr("vector.err_no_context_export"), "error")
            return

        export_data = {
            "type": ds.get("geom_type", "Point"),
            "features": ds.get("features", []),
        }

        if fmt == "dxf":
            ok = self._ctx.vector_service.save_dxf(export_data, path)
        else:
            ok = self._ctx.vector_service.save(export_data, path)

        if ok:
            notify(self, tr("vector.info_exported", path=path), "info")
        else:
            notify(self, tr("vector.err_export_failed", path=path), "error")

    # ======================================================================
    # i18n
    # ======================================================================

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        # Group boxes
        self._file_card.setTitle(tr("vector.file_operations"))
        self._edit_tools_card.setTitle(tr("vector.edit_tools"))
        self._layer_card.setTitle(tr("vector.layer_management"))
        self._property_card.setTitle(tr("vector.property_editor"))

        # File ops buttons
        self._btn_load_shp.setText(tr("vector.load_vector"))
        self._btn_new_layer.setText(tr("vector.new_layer"))
        self._btn_load_base_image.setText(tr("vector.load_base_image"))
        self._btn_export_shp.setText(tr("vector.export_shp"))
        self._btn_export_geojson.setText(tr("vector.export_geojson"))
        self._btn_export_dxf.setText(tr("vector.export_dxf"))
        self._export_label.setText(tr("vector.export_label"))

        # Edit tools
        map_to_keys = {
            "select": "vector.select",
            "move": "vector.move",
            "draw_point": "vector.draw_point",
            "draw_line": "vector.draw_line",
            "draw_polygon": "vector.draw_polygon",
            "edit_vertices": "vector.edit_vertices",
        }
        for btn in self._tool_button_group.buttons():
            obj = btn.objectName()
            if obj in map_to_keys:
                btn.setText(tr(map_to_keys[obj]))

        self._btn_undo.setText(tr("vector.undo"))
        self._btn_redo.setText(tr("vector.redo"))

        # Layer management
        self._layer_tree.setHeaderLabels([tr("vector.col_layer"), tr("vector.col_features")])
        self._btn_delete_layer.setText(tr("vector.delete_layer"))

        # Property editor
        self._property_label.setText(tr("vector.no_feature_selected"))
        self._property_table.setHorizontalHeaderLabels([tr("vector.col_field"), tr("vector.col_value")])
        self._btn_add_field.setText(tr("vector.add_field"))
        self._btn_mod_field.setText(tr("vector.modify_field"))
        self._btn_del_field.setText(tr("vector.delete_field"))

        # Sidebar
        self._sidebar.retranslate_ui()

    # ======================================================================
    # State save / restore
    # ======================================================================

    def get_state(self) -> dict[str, Any]:
        """Return serializable state dict for persistence."""
        return {
            "datasets": [
                {
                    "id": ds["id"],
                    "name": ds["name"],
                    "path": ds.get("path", ""),
                    "geom_type": ds.get("geom_type", "Point"),
                    "features": ds.get("features", []),
                    "visible": ds.get("visible", True),
                }
                for ds in self._datasets
            ],
            "active_dataset_id": self._active_dataset_id,
            "selected_feature_id": self._selected_feature_id,
            "base_image_path": self._base_image_path,
            "mode": self._mode.value,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from a saved dict."""
        self._datasets.clear()
        self._feature_owners.clear()
        self._layer_groups.clear()

        for ds_data in state.get("datasets", []):
            ds = dict(ds_data)
            for f in ds.get("features", []):
                if not f.get("id"):
                    f["id"] = str(uuid.uuid4())
                self._feature_owners[f["id"]] = ds["id"]
            self._datasets.append(ds)

        self._active_dataset_id = state.get("active_dataset_id")
        self._selected_feature_id = state.get("selected_feature_id")

        base_path = state.get("base_image_path")
        if base_path:
            self._base_image_path = base_path
            self._viewer.load(base_path)
        else:
            self._viewer.load_blank(self._DEFAULT_CANVAS_SIZE,
                                    self._DEFAULT_CANVAS_SIZE, (40, 40, 40))

        mode_str = state.get("mode", "select")
        try:
            self._mode = EditMode(mode_str)
        except ValueError:
            self._mode = EditMode.SELECT

        # Sync tool buttons
        for btn in self._tool_button_group.buttons():
            if btn.objectName() == self._mode.value:
                btn.setChecked(True)
                break

        self._rebuild_overlays()
        self._refresh_layer_tree()
        self._refresh_property_editor()
        self._clear_highlight()
        if self._selected_feature_id is not None:
            self._highlight_feature(self._selected_feature_id)

        # Clear undo/redo
        self._undo_stack.clear()
        self._redo_stack.clear()
