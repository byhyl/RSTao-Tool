"""Object detection tab with model management and result visualization.

Layout:
  Left: model management (QComboBox for model list, load button,
        confidence/IoU spin boxes, run/export buttons)
  Right: RasterViewer with detection overlay (bounding boxes via add_rect/add_text)

Signals:
    statusMessage(str): emitted for status bar updates
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..task_runner import run_background
from ..widgets.raster_viewer import RasterViewer
from ..widgets.raster_viewer_sidebar import RasterViewerSidebar


DEFAULT_CONFIDENCE = 0.50
DEFAULT_IOU = 0.45


class DetectionTab(QWidget):
    """Object detection tab using ONNX models with bounding-box overlay."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = self._resolve_context()
        self._service = self._ctx.detection_service

        # -- state ----------------------------------------------------------
        self._current_image: np.ndarray | None = None
        self._current_image_path: str = ""
        self._last_output: Any = None
        self._models: dict[str, Any] = {}
        self._loaded_model_path: str = ""

        self._setup_ui()
        self._connect_signals()
        self._refresh_model_list()

    def _resolve_context(self):
        """Walk up to the MainWindow to get the AppContext."""
        w = self.window()
        if hasattr(w, "_ctx"):
            return w._ctx
        from application import AppContext
        return AppContext()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)

        # -- Left panel ----------------------------------------------------
        left_panel = QWidget()
        left_panel.setMinimumWidth(300)
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._build_model_card())
        left_layout.addWidget(self._build_action_card())
        left_layout.addStretch()

        # -- Right panel: detection viewer + sidebar -------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel(tr("detection.image_viewer")))

        viewer_row = QHBoxLayout()
        self.viewer = RasterViewer()
        viewer_row.addWidget(self.viewer, 1)
        self._sidebar = RasterViewerSidebar()
        self._sidebar.attach(self.viewer)
        viewer_row.addWidget(self._sidebar)
        right_layout.addLayout(viewer_row, 1)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

    # -- Cards ----------------------------------------------------------------

    def _build_model_card(self) -> QGroupBox:
        group = QGroupBox(tr("detection.model"))
        self._model_card = group
        layout = QVBoxLayout(group)

        # Model combo
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel(tr("detection.model_list")))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(160)
        combo_row.addWidget(self.model_combo, 1)
        layout.addLayout(combo_row)

        # Load button
        self.btn_load_model = QPushButton(tr("detection.load_model"))
        layout.addWidget(self.btn_load_model)

        # Confidence
        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel(tr("detection.confidence")))
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.01, 1.0)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(DEFAULT_CONFIDENCE)
        self.conf_spin.setDecimals(3)
        conf_row.addWidget(self.conf_spin)
        layout.addLayout(conf_row)

        # IoU
        iou_row = QHBoxLayout()
        iou_row.addWidget(QLabel(tr("detection.iou")))
        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.01, 1.0)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(DEFAULT_IOU)
        self.iou_spin.setDecimals(3)
        iou_row.addWidget(self.iou_spin)
        layout.addLayout(iou_row)

        return group

    def _build_action_card(self) -> QGroupBox:
        group = QGroupBox(tr("detection.operations"))
        self._action_card = group
        layout = QVBoxLayout(group)

        self.btn_load_image = QPushButton(tr("detection.select_image"))
        self.btn_run = QPushButton(tr("detection.run"))
        self.btn_export = QPushButton(tr("detection.export"))

        layout.addWidget(self.btn_load_image)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.btn_export)
        return group

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.btn_load_model.clicked.connect(self._on_load_model)
        self.btn_load_image.clicked.connect(self._on_load_image)
        self.btn_run.clicked.connect(self._on_run_detection)
        self.btn_export.clicked.connect(self._on_export)

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _refresh_model_list(self) -> None:
        """Populate the model combo from the ModelRegistry."""
        self.model_combo.clear()
        self._models = self._service.list_models()
        if not self._models:
            self.model_combo.addItem(tr("detection.no_model"))
            return

        for path, config in self._models.items():
            label = config.name or Path(path).name
            self.model_combo.addItem(label, path)

    def _on_load_model(self) -> None:
        idx = self.model_combo.currentIndex()
        path = self.model_combo.currentData()
        if not path:
            # Prompt for a new ONNX model file
            path, _ = QFileDialog.getOpenFileName(
                self,
                tr("detection.select_model"),
                "",
                "ONNX Models (*.onnx);;All Files (*.*)",
            )
            if not path:
                return

        success = self._service.load_model(path)
        if not success:
            self.statusMessage.emit(tr("detection.load_failed", path=path))
            return

        self._loaded_model_path = path

        # Infer and save config with current confidence/iou
        config = self._service.infer_config(
            path,
            confidence=self.conf_spin.value(),
            iou_threshold=self.iou_spin.value(),
        )
        self._service.apply_config(config)
        self._service.save_model_config(config)

        # Refresh model list to include newly loaded model
        self._refresh_model_list()
        # Select the loaded model in combobox
        for i in range(self.model_combo.count()):
            if self.model_combo.itemData(i) == path:
                self.model_combo.setCurrentIndex(i)
                break

        name = config.name or Path(path).name
        self.statusMessage.emit(tr("detection.loaded", name=name))

    # ------------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------------

    def _on_load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("detection.select_image"),
            "",
            tr("filter.resources"),
        )
        if not path:
            return

        from data.image_io import read_image
        arr = read_image(path)
        if arr is None:
            self.statusMessage.emit(tr("detection.load_failed", path=path))
            return

        self._current_image = arr
        self._current_image_path = path
        self.viewer.load_from_array(arr)
        self.statusMessage.emit(tr("detection.loaded", name=Path(path).name))

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def _on_run_detection(self) -> None:
        if self._current_image is None:
            QMessageBox.warning(
                self, tr("detection.title"), tr("detection.no_image")
            )
            return

        if not self._service.available:
            QMessageBox.warning(
                self, tr("detection.title"), tr("detection.model_not_loaded")
            )
            return

        # Apply current confidence / IoU before inference
        config = self._service.infer_config(
            self._loaded_model_path or "",
            confidence=self.conf_spin.value(),
            iou_threshold=self.iou_spin.value(),
        )
        self._service.apply_config(config)

        image = self._current_image

        def _task() -> Any:
            return self._service.detect(image)

        run_background(
            target=_task,
            on_done=self._on_detection_done,
            on_error=self._on_detection_error,
            parent=self,
        )

    def _on_detection_done(self, output: Any) -> None:
        self._last_output = output
        self._draw_detections(output)

        # Extract boxes from results list (DetectionOutput.results)
        count = 0
        if hasattr(output, "results"):
            count = len(output.results) if output.results else 0
        elif isinstance(output, dict):
            results = output.get("results") or output.get("bboxes") or output.get("boxes") or []
            count = len(results)
        self.statusMessage.emit(tr("detection.inference_done", count=count))

    def _on_detection_error(self, err: str) -> None:
        self.statusMessage.emit(tr("detection.inference_failed", error=err))
        QMessageBox.critical(
            self, tr("detection.title"), tr("detection.inference_failed", error=err)
        )

    def _draw_detections(self, output: Any) -> None:
        """Overlay bounding boxes and labels on the current image."""
        if self._current_image is None:
            return

        # Reload the base image into the viewer
        self.viewer.load_from_array(self._current_image)
        self.viewer.clear_overlays()

        # Extract detection results (list of DetectionResult objects)
        results = []
        if hasattr(output, "results"):
            results = output.results or []
        elif isinstance(output, dict):
            results = output.get("results") or output.get("bboxes") or output.get("boxes") or []

        for i, det in enumerate(results):
            box = None
            label = ""
            score = 0.0

            if hasattr(det, "bbox"):
                box = det.bbox
                label = getattr(det, "class_name", "") or str(getattr(det, "class_id", ""))
                score = getattr(det, "score", 0.0)
            elif isinstance(det, (list, tuple)) and len(det) >= 4:
                box = det[:4]
            elif hasattr(det, "tolist"):
                arr = np.asarray(det).flatten()
                box = arr[:4]
            else:
                continue

            text = f"{label} {score:.2f}" if label else f"{score:.2f}"

            self.viewer.add_rect(
                float(x1), float(y1), float(x2), float(y2),
                color="lime",
                width=2.0,
                label=text,
            )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        if self._current_image is None or self._last_output is None:
            QMessageBox.warning(
                self, tr("detection.title"), tr("detection.export_no_result")
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("detection.export"),
            "detection_result.png",
            "PNG Images (*.png);;JPEG Images (*.jpg);;All Files (*.*)",
        )
        if not path:
            return

        # Draw detections onto a copy and save
        try:
            result_img = self._service.draw(self._current_image, self._last_output)
            from data.image_io import save_image
            save_image(path, result_img)
            self.statusMessage.emit(tr("detection.export_done", path=path))
        except Exception as exc:
            self.statusMessage.emit(tr("detection.export_failed", error=str(exc)))

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return serialisable state for project save."""
        return {
            "image_path": self._current_image_path,
            "confidence": self.conf_spin.value(),
            "iou_threshold": self.iou_spin.value(),
        }

    def set_state(self, state: dict) -> None:
        """Restore tab state from a loaded project."""
        if not state:
            return

        self.conf_spin.setValue(
            float(state.get("confidence", DEFAULT_CONFIDENCE))
        )
        self.iou_spin.setValue(
            float(state.get("iou_threshold", DEFAULT_IOU))
        )

        image_path = state.get("image_path", "")
        if image_path:
            from data.image_io import read_image
            import os
            if os.path.exists(image_path):
                arr = read_image(image_path)
                if arr is not None:
                    self._current_image = arr
                    self._current_image_path = image_path
                    self.viewer.load_from_array(arr)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        self._model_card.setTitle(tr("detection.model"))
        self._action_card.setTitle(tr("detection.operations"))

        # Buttons
        self.btn_load_model.setText(tr("detection.load_model"))
        self.btn_load_image.setText(tr("detection.select_image"))
        self.btn_run.setText(tr("detection.run"))
        self.btn_export.setText(tr("detection.export"))

        # Model combo placeholder (if no models loaded)
        if self.model_combo.count() == 0:
            self.model_combo.addItem(tr("detection.no_model"))
        elif self.model_combo.itemText(0) in (tr("detection.no_model"), "No model selected"):
            self.model_combo.setItemText(0, "")
            # Re-check and refresh from model list
            self._refresh_model_list()

        # Sidebar
        if self._sidebar is not None:
            self._sidebar.retranslate_ui()
