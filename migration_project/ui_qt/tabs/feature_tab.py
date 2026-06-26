"""Feature detection tab -- QWidget-based UI for geometric transform and feature detection.

Replaces ui/feature_tab.py (customtkinter-based).
"""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from application import AppContext
from common.exceptions import AlgorithmError
from common.logger import logger
from ui_qt.helpers import notify, raster_geo_transform
from ui_qt.widgets.raster_viewer import RasterViewer
from ui_qt.i18n import tr


class FeatureTab(QWidget):
    """Feature detection and geometric transform tab.

    Layout:
        Left panel (QScrollArea): image management, geometric transform card,
            feature detection card, statistics card.
        Right panel: two RasterViewer instances (original + detected overlay).
    """

    # -- threshold config per method ----------------------------------------
    _THRESH_CFG: dict[str, dict[str, float]] = {
        "harris":   {"min": 0.001, "max": 0.1, "step": 0.001, "default": 0.01},
        "moravec":  {"min": 0.01,  "max": 0.2, "step": 0.005, "default": 0.05},
        "forstner": {"min": 0.0005,"max": 0.02,"step": 0.0005,"default": 0.001},
        "susan":    {"min": 0.05,  "max": 0.5, "step": 0.01,  "default": 0.2},
    }

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        # -- internal state -------------------------------------------------
        self._original_img: np.ndarray | None = None
        self._result_img: np.ndarray | None = None
        self._image_path: str = ""
        self._geo_transform: object = None

        # -- feature service (lazy) -----------------------------------------
        self._feature_service = ctx.feature_service

        # -- debounce timer for real-time rendering -------------------------
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(200)
        self._render_timer.timeout.connect(self._do_render)

        # -- build UI -------------------------------------------------------
        self._init_ui()
        self._connect_realtime()

    # ======================================================================
    #  UI construction
    # ======================================================================

    def _init_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- left panel: scroll area --------------------------------------
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setMinimumWidth(280)
        self._left_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self._build_image_card(left_layout)
        self._build_geom_card(left_layout)
        self._build_feature_card(left_layout)
        self._build_stats_card(left_layout)
        left_layout.addStretch()

        self._left_scroll.setWidget(left_container)

        # --- right panel: two RasterViewers --------------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)

        viewers_row = QHBoxLayout()
        viewers_row.setSpacing(4)

        # Original viewer
        orig_container = QWidget()
        orig_layout = QVBoxLayout(orig_container)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_layout.setSpacing(2)
        orig_label = QLabel(tr("feature.original_image"))
        self._orig_label = orig_label
        orig_label.setStyleSheet("color: #888; font-size: 10px;")
        orig_layout.addWidget(orig_label)
        self._viewer_original = RasterViewer()
        orig_layout.addWidget(self._viewer_original)

        # Result viewer
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(2)
        result_label = QLabel(tr("feature.result_image"))
        self._result_label = result_label
        result_label.setStyleSheet("color: #888; font-size: 10px;")
        result_layout.addWidget(result_label)
        self._viewer_result = RasterViewer()
        result_layout.addWidget(self._viewer_result)

        viewers_row.addWidget(orig_container, 1)
        viewers_row.addWidget(result_container, 1)

        right_layout.addLayout(viewers_row)

        # --- assemble main layout ------------------------------------------
        main_layout.addWidget(self._left_scroll, 0)
        main_layout.addWidget(right_panel, 1)

    # -- image management card ----------------------------------------------

    def _build_image_card(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(tr("feature.image_management"))
        self._img_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        btn_row = QHBoxLayout()
        self._btn_load = QPushButton(tr("feature.load_image"))
        self._btn_load.clicked.connect(self._on_load_image)
        btn_row.addWidget(self._btn_load)

        self._btn_save = QPushButton(tr("feature.save_result"))
        self._btn_save.clicked.connect(self._on_save_result)
        btn_row.addWidget(self._btn_save)

        layout.addLayout(btn_row)

        self._btn_clear = QPushButton(tr("feature.clear"))
        self._btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self._btn_clear)

        parent_layout.addWidget(group)

    # -- geometric transform card -------------------------------------------

    def _build_geom_card(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(tr("feature.geometric_transform"))
        self._geom_card = group
        form = QFormLayout(group)
        form.setSpacing(6)

        # rotation angle
        self._spin_angle = QDoubleSpinBox()
        self._spin_angle.setRange(-180.0, 180.0)
        self._spin_angle.setSingleStep(1.0)
        self._spin_angle.setValue(0.0)
        self._spin_angle.setSuffix("°")
        self._label_angle = QLabel(tr("feature.rotation_angle"))
        form.addRow(self._label_angle, self._spin_angle)

        # scale ratio
        self._spin_scale = QDoubleSpinBox()
        self._spin_scale.setRange(0.2, 2.0)
        self._spin_scale.setSingleStep(0.05)
        self._spin_scale.setValue(1.0)
        self._label_scale = QLabel(tr("feature.scale_ratio"))
        form.addRow(self._label_scale, self._spin_scale)

        # interpolation method
        self._combo_interp = QComboBox()
        self._combo_interp.addItem(tr("feature.interp_bilinear"), "bilinear")
        self._combo_interp.addItem(tr("feature.interp_bicubic"), "bicubic")
        self._label_interp = QLabel(tr("feature.interpolation"))
        form.addRow(self._label_interp, self._combo_interp)

        parent_layout.addWidget(group)

    # -- feature detection card ---------------------------------------------

    def _build_feature_card(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(tr("feature.feature_detection"))
        self._feat_card = group
        form = QFormLayout(group)
        form.setSpacing(6)

        # method selector
        self._combo_method = QComboBox()
        self._combo_method.addItem(tr("feature.method_harris"), "harris")
        self._combo_method.addItem(tr("feature.method_susan"), "susan")
        self._combo_method.addItem(tr("feature.method_moravec"), "moravec")
        self._combo_method.addItem(tr("feature.method_forstner"), "forstner")
        self._combo_method.currentIndexChanged.connect(self._on_method_changed)
        self._label_method = QLabel(tr("feature.detection_method"))
        form.addRow(self._label_method, self._combo_method)

        # Harris k (visible only for Harris)
        self._spin_harris_k = QDoubleSpinBox()
        self._spin_harris_k.setRange(0.01, 0.1)
        self._spin_harris_k.setSingleStep(0.001)
        self._spin_harris_k.setDecimals(3)
        self._spin_harris_k.setValue(0.04)
        self._label_harris_k = QLabel(tr("feature.harris_k"))
        form.addRow(self._label_harris_k, self._spin_harris_k)

        # SUSAN t (visible only for SUSAN)
        self._spin_susan_t = QSpinBox()
        self._spin_susan_t.setRange(5, 50)
        self._spin_susan_t.setValue(25)
        self._label_susan_t = QLabel(tr("feature.susan_t"))
        form.addRow(self._label_susan_t, self._spin_susan_t)

        # threshold slider (dynamic range per method)
        self._slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self._slider_threshold.setRange(0, 1000)  # normalized 0..1000
        self._slider_threshold.setValue(500)
        self._spin_threshold = QDoubleSpinBox()
        self._spin_threshold.setDecimals(4)
        self._spin_threshold.setValue(0.01)
        # bidirectional binding
        self._slider_threshold.valueChanged.connect(self._on_threshold_slider_changed)
        self._spin_threshold.valueChanged.connect(self._on_threshold_spin_changed)
        thresh_row = QHBoxLayout()
        thresh_row.addWidget(self._slider_threshold, 1)
        thresh_row.addWidget(self._spin_threshold)
        self._label_threshold = QLabel(tr("feature.threshold"))
        form.addRow(self._label_threshold, thresh_row)
        self._threshold_slider_locked = False

        # point size
        self._spin_point_size = QSpinBox()
        self._spin_point_size.setRange(1, 10)
        self._spin_point_size.setValue(4)
        self._label_point_size = QLabel(tr("feature.point_size"))
        form.addRow(self._label_point_size, self._spin_point_size)

        # real-time checkbox
        self._chk_realtime = QCheckBox(tr("feature.real_time"))
        self._chk_realtime.setChecked(True)
        form.addRow("", self._chk_realtime)

        parent_layout.addWidget(group)

        # initial visibility
        self._update_method_param_visibility()

    # -- statistics card ----------------------------------------------------

    def _build_stats_card(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(tr("feature.statistics"))
        self._stats_card = group
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._lbl_feature_count = QLabel(tr("feature.count", count=0))
        self._lbl_feature_count.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        self._lbl_feature_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lbl_feature_count)

        parent_layout.addWidget(group)

    # ======================================================================
    #  Signal / slot wiring (real-time)
    # ======================================================================

    def _connect_realtime(self) -> None:
        """Connect all parameter widgets' valueChanged signals to debounced render."""
        # geometric params
        self._spin_angle.valueChanged.connect(self._schedule_render)
        self._spin_scale.valueChanged.connect(self._schedule_render)
        self._combo_interp.currentIndexChanged.connect(self._schedule_render)

        # feature params
        self._combo_method.currentIndexChanged.connect(self._schedule_render)
        self._spin_harris_k.valueChanged.connect(self._schedule_render)
        self._spin_susan_t.valueChanged.connect(self._schedule_render)
        self._spin_threshold.valueChanged.connect(self._schedule_render)
        self._spin_point_size.valueChanged.connect(self._schedule_render)
        self._chk_realtime.toggled.connect(self._on_realtime_toggled)

    def _schedule_render(self, *_args: Any) -> None:
        """Schedule a debounced render if real-time mode is on."""
        if not self._chk_realtime.isChecked():
            return
        if self._original_img is None:
            return
        self._render_timer.start()

    def _on_realtime_toggled(self, checked: bool) -> None:
        if checked and self._original_img is not None:
            self._schedule_render()

    # -- method-specific parameter visibility -------------------------------

    def _on_method_changed(self, _index: int = 0) -> None:
        self._update_method_param_visibility()
        self._update_threshold_range()
        self._schedule_render()

    def _update_method_param_visibility(self) -> None:
        method = self._combo_method.currentData()
        # Harris k
        self._label_harris_k.setVisible(method == "harris")
        self._spin_harris_k.setVisible(method == "harris")
        # SUSAN t
        self._label_susan_t.setVisible(method == "susan")
        self._spin_susan_t.setVisible(method == "susan")

    def _update_threshold_range(self) -> None:
        method = self._combo_method.currentData()
        cfg = self._THRESH_CFG.get(method, self._THRESH_CFG["harris"])
        self._spin_threshold.blockSignals(True)
        self._spin_threshold.setRange(cfg["min"], cfg["max"])
        self._spin_threshold.setSingleStep(cfg["step"])
        self._spin_threshold.setValue(cfg["default"])
        self._spin_threshold.setDecimals(max(4, len(str(cfg["step"]).split(".")[-1])))
        self._spin_threshold.blockSignals(False)
        # update slider to match
        self._threshold_slider_locked = True
        self._slider_threshold.setValue(
            self._threshold_to_slider(cfg["default"], cfg["min"], cfg["max"])
        )
        self._threshold_slider_locked = False

    def _on_threshold_slider_changed(self, value: int) -> None:
        if self._threshold_slider_locked:
            return
        cfg = self._THRESH_CFG.get(
            self._combo_method.currentData(), self._THRESH_CFG["harris"]
        )
        actual = self._slider_to_threshold(value, cfg["min"], cfg["max"])
        self._spin_threshold.blockSignals(True)
        self._spin_threshold.setValue(actual)
        self._spin_threshold.blockSignals(False)
        self._schedule_render()

    def _on_threshold_spin_changed(self, value: float) -> None:
        cfg = self._THRESH_CFG.get(
            self._combo_method.currentData(), self._THRESH_CFG["harris"]
        )
        self._threshold_slider_locked = True
        self._slider_threshold.setValue(self._threshold_to_slider(value, cfg["min"], cfg["max"]))
        self._threshold_slider_locked = False
        self._schedule_render()

    @staticmethod
    def _threshold_to_slider(value: float, vmin: float, vmax: float) -> int:
        if vmax <= vmin:
            return 0
        return int(round((value - vmin) / (vmax - vmin) * 1000))

    @staticmethod
    def _slider_to_threshold(slider_val: int, vmin: float, vmax: float) -> float:
        return vmin + (slider_val / 1000.0) * (vmax - vmin)

    # ======================================================================
    #  Image loading / saving
    # ======================================================================

    def _on_load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("feature.load_image_title"),
            "",
            tr("feature.image_filter"),
        )
        if not path:
            return
        try:
            self._load_image_from_path(path)
        except Exception as exc:
            logger.exception("Failed to load image")
            QMessageBox.critical(
                self,
                tr("feature.load_image_title"),
                tr("feature.load_image_failed", error=str(exc)),
            )

    def load_image_silent(self, path: str, preview: bool = True) -> None:
        """Entry point from drag-drop or external callers."""
        self._load_image_from_path(path)

    def _load_image_from_path(self, path: str) -> None:
        self._image_path = path
        self._original_img = self._feature_service.load_image(path)
        if self._original_img is None:
            raise AlgorithmError(tr("feature.load_image_failed", error="unknown"))

        # Try to extract geo transform
        gt = raster_geo_transform(path)
        if gt is not None:
            self._geo_transform = gt
        else:
            self._geo_transform = None

        self._update_viewers()

    def _on_clear(self) -> None:
        self._original_img = None
        self._result_img = None
        self._image_path = ""
        self._geo_transform = None
        self._viewer_original.clear_image()
        self._viewer_result.clear_image()
        self._lbl_feature_count.setText(tr("feature.count", count=0))

    def _on_save_result(self) -> None:
        if self._result_img is None:
            QMessageBox.information(
                self,
                tr("feature.save_result_title"),
                tr("feature.no_result_to_save"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("feature.save_result_title"),
            "",
            tr("feature.save_filter"),
        )
        if not path:
            return

        try:
            # Convert RGB back to BGR for saving if needed
            save_img = cv2.cvtColor(self._result_img, cv2.COLOR_RGB2BGR)
            self._feature_service.save_image(save_img, path)
            notify(self, tr("feature.save_success", path=os.path.basename(path)))
        except Exception as exc:
            logger.exception("Failed to save result")
            QMessageBox.critical(
                self,
                tr("feature.save_result_title"),
                tr("feature.save_failed", error=str(exc)),
            )

    # ======================================================================
    #  Rendering
    # ======================================================================

    def _do_render(self) -> None:
        """Core rendering: apply geometric transform + feature detection."""
        if self._original_img is None:
            return

        # Read current parameter values
        angle = self._spin_angle.value()
        scale = self._spin_scale.value()
        interp = self._combo_interp.currentData()
        method = self._combo_method.currentData()
        threshold = self._spin_threshold.value()
        point_size = self._spin_point_size.value()

        try:
            # Step 1: rotate + scale (BGR image from load_image)
            img_bgr = self._original_img.copy()
            rotated = self._feature_service.rotate(img_bgr, angle, scale, interp)

            # Step 2: convert to gray for detection
            gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)

            # Step 3: feature detection
            if method == "harris":
                harris_k = self._spin_harris_k.value()
                mask, cnt = self._feature_service.harris(gray, harris_k, threshold)
            elif method == "moravec":
                mask, cnt = self._feature_service.moravec(gray, threshold)
            elif method == "forstner":
                mask, cnt = self._feature_service.forstner(gray, threshold)
            else:  # susan
                susan_t = self._spin_susan_t.value()
                mask, cnt = self._feature_service.susan(gray, susan_t, threshold)

            # Step 4: draw points on the rotated BGR image
            drawn_bgr = self._feature_service.draw_points(rotated, mask, point_size)

            # Step 5: convert to RGB for display
            self._result_img = cv2.cvtColor(drawn_bgr, cv2.COLOR_BGR2RGB)

            # Step 6: update viewers
            self._update_viewers()

            # Step 7: update stats
            self._lbl_feature_count.setText(tr("feature.count", count=cnt))

        except Exception as exc:
            logger.exception("Render failed")
            self._lbl_feature_count.setText(tr("feature.render_error"))
            # Still show original on left, blank on right
            self._update_viewers(only_original=True)

    def _update_viewers(self, only_original: bool = False) -> None:
        """Push current images to the RasterViewer widgets."""
        if self._original_img is not None:
            rgb_orig = cv2.cvtColor(self._original_img, cv2.COLOR_BGR2RGB)
            self._viewer_original.load_from_array(rgb_orig)

        if not only_original and self._result_img is not None:
            self._viewer_result.load_from_array(self._result_img)
        elif only_original:
            self._viewer_result.clear_image()

    # ======================================================================
    #  Project persistence
    # ======================================================================

    def get_state(self) -> dict[str, Any]:
        """Return serializable state for project save."""
        return {
            "image_path": self._image_path,
            "angle": self._spin_angle.value(),
            "scale_ratio": self._spin_scale.value(),
            "interp_method": self._combo_interp.currentData(),
            "feature_method": self._combo_method.currentData(),
            "point_size": self._spin_point_size.value(),
            "real_time": self._chk_realtime.isChecked(),
            "harris_k": self._spin_harris_k.value(),
            "susan_t": self._spin_susan_t.value(),
            "threshold": self._spin_threshold.value(),
        }

    def set_state(self, state: dict[str, Any] | None) -> None:
        """Restore tab state from a project file."""
        if not state:
            return

        # Restore parameters (block signals during bulk restore)
        self._chk_realtime.blockSignals(True)

        self._spin_angle.setValue(state.get("angle", 0.0))
        self._spin_scale.setValue(state.get("scale_ratio", 1.0))

        interp = state.get("interp_method", "bilinear")
        idx = self._combo_interp.findData(interp)
        if idx >= 0:
            self._combo_interp.setCurrentIndex(idx)

        method = state.get("feature_method", "harris")
        idx = self._combo_method.findData(method)
        if idx >= 0:
            self._combo_method.setCurrentIndex(idx)

        self._spin_point_size.setValue(state.get("point_size", 4))
        self._chk_realtime.setChecked(state.get("real_time", True))
        self._spin_harris_k.setValue(state.get("harris_k", 0.04))
        self._spin_susan_t.setValue(state.get("susan_t", 25))
        self._spin_threshold.setValue(state.get("threshold", 0.01))

        self._chk_realtime.blockSignals(False)

        # Update visibility / threshold range for the restored method
        self._update_method_param_visibility()
        self._update_threshold_range()

        # Restore image
        image_path = state.get("image_path", "")
        if image_path and os.path.exists(image_path):
            try:
                self._image_path = image_path
                self._original_img = self._feature_service.load_image(image_path)
                gt = raster_geo_transform(image_path)
                if gt is not None:
                    self._geo_transform = gt
                self._do_render()
            except Exception as exc:
                logger.warning("Failed to restore image from state: %s", exc)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        # Group boxes
        self._img_card.setTitle(tr("feature.image_management"))
        self._geom_card.setTitle(tr("feature.geometric_transform"))
        self._feat_card.setTitle(tr("feature.feature_detection"))
        self._stats_card.setTitle(tr("feature.statistics"))

        # Buttons
        self._btn_load.setText(tr("feature.load_image"))
        self._btn_save.setText(tr("feature.save_result"))
        self._btn_clear.setText(tr("feature.clear"))

        # Form labels
        self._label_angle.setText(tr("feature.rotation_angle"))
        self._label_scale.setText(tr("feature.scale_ratio"))
        self._label_interp.setText(tr("feature.interpolation"))
        self._label_method.setText(tr("feature.detection_method"))
        self._label_harris_k.setText(tr("feature.harris_k"))
        self._label_susan_t.setText(tr("feature.susan_t"))
        self._label_threshold.setText(tr("feature.threshold"))
        self._label_point_size.setText(tr("feature.point_size"))

        # Combo items (data-preserving)
        interp_idx = self._combo_interp.currentIndex()
        self._combo_interp.clear()
        self._combo_interp.addItem(tr("feature.interp_bilinear"), "bilinear")
        self._combo_interp.addItem(tr("feature.interp_bicubic"), "bicubic")
        if interp_idx >= 0:
            self._combo_interp.setCurrentIndex(interp_idx)

        method_idx = self._combo_method.currentIndex()
        self._combo_method.clear()
        self._combo_method.addItem(tr("feature.method_harris"), "harris")
        self._combo_method.addItem(tr("feature.method_susan"), "susan")
        self._combo_method.addItem(tr("feature.method_moravec"), "moravec")
        self._combo_method.addItem(tr("feature.method_forstner"), "forstner")
        if method_idx >= 0:
            self._combo_method.setCurrentIndex(method_idx)

        # Checkbox
        self._chk_realtime.setText(tr("feature.real_time"))

        # Viewer labels
        self._orig_label.setText(tr("feature.original_image"))
        self._result_label.setText(tr("feature.result_image"))

        # Stats label — dynamic text populated by _do_render / _on_clear,
        # so no explicit update needed here.
