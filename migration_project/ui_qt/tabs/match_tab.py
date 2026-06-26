"""Image matching tab with template management, search, and result visualization.

Layout:
  Left: QScrollArea with cards (template management, search area, parameters,
        operations, statistics)
  Right: 2x2 QGridLayout — template RasterViewer, search RasterViewer,
         result RasterViewer, correlation heatmap (matplotlib FigureCanvasQTAgg)

Signals:
    statusMessage(str): emitted for status bar updates
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..i18n import tr
from ..task_runner import run_background
from ..widgets.raster_viewer import RasterViewer


DEFAULT_MATCH_THRESHOLD = 0.80
DEFAULT_NMS_THRESHOLD = 0.50


class MatchTab(QWidget):
    """Image template matching tab with template management and result viewing."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = self._resolve_context()
        self._service = self._ctx.matching_service

        # -- state ----------------------------------------------------------
        self._template_paths: list[str] = []
        self._template_arrays: list[np.ndarray] = []
        self._search_path: str = ""
        self._search_array: np.ndarray | None = None
        self._last_result: dict[str, Any] | None = None
        self._heatmap_data: np.ndarray | None = None
        self._heatmap_canvas: FigureCanvasQTAgg | None = None
        self._heatmap_figure: Figure | None = None

        self._setup_ui()
        self._connect_signals()

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

        # -- Left panel: scrollable cards --------------------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(320)
        left_scroll.setMaximumWidth(420)
        left_inner = QWidget()
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._build_template_card())
        left_layout.addWidget(self._build_search_card())
        left_layout.addWidget(self._build_parameter_card())
        left_layout.addWidget(self._build_operation_card())
        left_layout.addWidget(self._build_statistics_card())
        left_layout.addStretch()

        left_scroll.setWidget(left_inner)

        # -- Right panel: 2x2 viewer grid ---------------------------------
        right_widget = QWidget()
        right_grid = QGridLayout(right_widget)
        right_grid.setContentsMargins(0, 0, 0, 0)
        right_grid.setSpacing(4)

        self.template_viewer = RasterViewer()
        self.template_viewer.setMinimumSize(300, 200)
        self.search_viewer = RasterViewer()
        self.search_viewer.setMinimumSize(300, 200)
        self.result_viewer = RasterViewer()
        self.result_viewer.setMinimumSize(300, 200)

        # Placeholder label for heatmap — replaced once FigureCanvas is created
        self.heatmap_placeholder = QLabel(tr("match.heatmap_placeholder"))
        self.heatmap_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heatmap_placeholder.setStyleSheet("color: #888;")

        self._template_viewer_label = QLabel(tr("match.template_viewer"))
        self._search_viewer_label = QLabel(tr("match.search_viewer"))
        self._result_viewer_label = QLabel(tr("match.result_viewer"))
        self._heatmap_label = QLabel(tr("match.heatmap"))

        right_grid.addWidget(self._template_viewer_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        right_grid.addWidget(self.template_viewer, 1, 0)
        right_grid.addWidget(self._search_viewer_label, 0, 1, Qt.AlignmentFlag.AlignCenter)
        right_grid.addWidget(self.search_viewer, 1, 1)
        right_grid.addWidget(self._result_viewer_label, 2, 0, Qt.AlignmentFlag.AlignCenter)
        right_grid.addWidget(self.result_viewer, 2, 1)
        right_grid.addWidget(self._heatmap_label, 3, 0, Qt.AlignmentFlag.AlignCenter)
        right_grid.addWidget(self.heatmap_placeholder, 3, 1)

        right_grid.setRowStretch(0, 0)
        right_grid.setRowStretch(1, 1)
        right_grid.setRowStretch(2, 1)
        right_grid.setRowStretch(3, 1)
        right_grid.setColumnStretch(0, 1)
        right_grid.setColumnStretch(1, 1)

        # Assemble ---------------------------------------------------------
        main_layout.addWidget(left_scroll)
        main_layout.addWidget(right_widget, 1)

    # -- Cards ----------------------------------------------------------------

    def _build_template_card(self) -> QGroupBox:
        group = QGroupBox(tr("match.templates"))
        self._template_card = group
        layout = QVBoxLayout(group)

        self.template_tree = QTreeWidget()
        self.template_tree.setHeaderLabels([tr("match.template_name"), tr("match.template_size")])
        self.template_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        btn_row = QHBoxLayout()
        self.btn_add_template = QPushButton(tr("match.add_template"))
        self.btn_remove_template = QPushButton(tr("match.remove_template"))
        self.btn_clear_templates = QPushButton(tr("match.clear_templates"))
        btn_row.addWidget(self.btn_add_template)
        btn_row.addWidget(self.btn_remove_template)
        btn_row.addWidget(self.btn_clear_templates)

        layout.addWidget(self.template_tree)
        layout.addLayout(btn_row)
        return group

    def _build_search_card(self) -> QGroupBox:
        group = QGroupBox(tr("match.search_image"))
        self._search_card = group
        layout = QHBoxLayout(group)

        self.btn_load_search = QPushButton(tr("match.load_search"))
        self.search_path_label = QLabel(tr("match.no_search_loaded"))
        self.search_path_label.setWordWrap(True)

        layout.addWidget(self.btn_load_search)
        layout.addWidget(self.search_path_label, 1)
        return group

    def _build_parameter_card(self) -> QGroupBox:
        group = QGroupBox(tr("match.parameters"))
        self._parameter_card = group
        layout = QVBoxLayout(group)

        # Threshold
        thr_row = QHBoxLayout()
        self._threshold_label = QLabel(tr("match.threshold"))
        thr_row.addWidget(self._threshold_label)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(DEFAULT_MATCH_THRESHOLD)
        self.threshold_spin.setDecimals(3)
        thr_row.addWidget(self.threshold_spin)
        layout.addLayout(thr_row)

        # NMS threshold
        nms_row = QHBoxLayout()
        self._nms_label = QLabel(tr("match.nms_threshold"))
        nms_row.addWidget(self._nms_label)
        self.nms_spin = QDoubleSpinBox()
        self.nms_spin.setRange(0.0, 1.0)
        self.nms_spin.setSingleStep(0.05)
        self.nms_spin.setValue(DEFAULT_NMS_THRESHOLD)
        self.nms_spin.setDecimals(3)
        nms_row.addWidget(self.nms_spin)
        layout.addLayout(nms_row)

        return group

    def _build_operation_card(self) -> QGroupBox:
        group = QGroupBox(tr("match.operations"))
        self._operation_card = group
        layout = QVBoxLayout(group)

        self.btn_single_match = QPushButton(tr("match.single_match"))
        self.btn_single_multi = QPushButton(tr("match.single_multi_match"))
        self.btn_multi_target = QPushButton(tr("match.multi_target_match"))

        layout.addWidget(self.btn_single_match)
        layout.addWidget(self.btn_single_multi)
        layout.addWidget(self.btn_multi_target)
        return group

    def _build_statistics_card(self) -> QGroupBox:
        group = QGroupBox(tr("match.statistics"))
        self._statistics_card = group
        layout = QVBoxLayout(group)

        self.lbl_match_count = QLabel(tr("match.match_count", count=0))
        self.lbl_scores = QLabel(tr("match.scores_none"))
        self.lbl_scores.setWordWrap(True)

        layout.addWidget(self.lbl_match_count)
        layout.addWidget(self.lbl_scores)
        return group

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.btn_add_template.clicked.connect(self._on_add_template)
        self.btn_remove_template.clicked.connect(self._on_remove_template)
        self.btn_clear_templates.clicked.connect(self._on_clear_templates)
        self.btn_load_search.clicked.connect(self._on_load_search)
        self.btn_single_match.clicked.connect(self._on_single_match)
        self.btn_single_multi.clicked.connect(self._on_single_multi)
        self.btn_multi_target.clicked.connect(self._on_multi_target)

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    def _on_add_template(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("match.select_template"),
            "",
            tr("filter.resources"),
        )
        if not paths:
            return
        for p in paths:
            if p not in self._template_paths:
                arr = self._service.load_image(p)
                if arr is None:
                    self.statusMessage.emit(tr("match.template_load_failed", path=p))
                    continue
                self._template_paths.append(p)
                self._template_arrays.append(arr)
                item = QTreeWidgetItem()
                item.setText(0, p.split("/")[-1].split("\\")[-1])
                item.setText(1, f"{arr.shape[1]}x{arr.shape[0]}")
                item.setData(0, Qt.ItemDataRole.UserRole, p)
                self.template_tree.addTopLevelItem(item)
                self.template_viewer.load_from_array(arr)

    def _on_remove_template(self) -> None:
        selected = self.template_tree.currentItem()
        if selected is None:
            return
        idx = self.template_tree.indexOfTopLevelItem(selected)
        if idx < 0:
            return
        self.template_tree.takeTopLevelItem(idx)
        del self._template_paths[idx]
        del self._template_arrays[idx]

    def _on_clear_templates(self) -> None:
        self.template_tree.clear()
        self._template_paths.clear()
        self._template_arrays.clear()
        self.template_viewer.clear_image()

    # ------------------------------------------------------------------
    # Search image
    # ------------------------------------------------------------------

    def _on_load_search(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("match.select_search"),
            "",
            tr("filter.resources"),
        )
        if not path:
            return
        arr = self._service.load_image(path)
        if arr is None:
            self.statusMessage.emit(tr("match.search_load_failed", path=path))
            return
        self._search_path = path
        self._search_array = arr
        import os
        self.search_path_label.setText(os.path.basename(path))
        self.search_viewer.load_from_array(arr)

    # ------------------------------------------------------------------
    # Matching operations
    # ------------------------------------------------------------------

    def _on_single_match(self) -> None:
        if not self._validate_inputs(single_template=True):
            return

        template = self._template_arrays[0]
        search = self._search_array
        threshold = self.threshold_spin.value()

        def _task() -> dict:
            return self._service.single_match(template, search, threshold)

        run_background(
            target=_task,
            on_done=self._on_match_done,
            on_error=self._on_match_error,
            parent=self,
        )

    def _on_single_multi(self) -> None:
        if not self._validate_inputs(single_template=True):
            return

        template = self._template_arrays[0]
        search = self._search_array
        threshold = self.threshold_spin.value()
        nms = self.nms_spin.value()

        def _task() -> dict:
            return self._service.single_multi_match(template, search, threshold, nms)

        run_background(
            target=_task,
            on_done=self._on_match_done,
            on_error=self._on_match_error,
            parent=self,
        )

    def _on_multi_target(self) -> None:
        if not self._validate_inputs(multi_template=True):
            return

        templates = list(self._template_arrays)
        search = self._search_array
        threshold = self.threshold_spin.value()

        def _task() -> dict:
            return self._service.multi_target_match(templates, search, threshold)

        run_background(
            target=_task,
            on_done=self._on_match_done,
            on_error=self._on_match_error,
            parent=self,
        )

    def _validate_inputs(self, single_template=False, multi_template=False) -> bool:
        if not self._template_arrays:
            QMessageBox.warning(self, tr("match.title"), tr("match.no_templates"))
            return False
        if single_template and len(self._template_arrays) < 1:
            QMessageBox.warning(self, tr("match.title"), tr("match.need_one_template"))
            return False
        if multi_template and len(self._template_arrays) < 1:
            QMessageBox.warning(self, tr("match.title"), tr("match.need_templates"))
            return False
        if self._search_array is None:
            QMessageBox.warning(self, tr("match.title"), tr("match.no_search"))
            return False
        return True

    # ------------------------------------------------------------------
    # Result handling
    # ------------------------------------------------------------------

    def _on_match_done(self, result: dict) -> None:
        self._last_result = result
        self._update_statistics(result)
        self._update_result_viewer(result)
        self._update_heatmap(result)
        self.statusMessage.emit(tr("match.done"))

    def _on_match_error(self, err: str) -> None:
        self.statusMessage.emit(tr("match.failed", error=err))
        QMessageBox.critical(self, tr("match.title"), tr("match.failed", error=err))

    def _update_statistics(self, result: dict) -> None:
        count = result.get("match_count", 0)
        scores = result.get("scores", [])
        self.lbl_match_count.setText(tr("match.match_count", count=count))
        if scores:
            formatted = ", ".join(f"{s:.4f}" for s in scores[:10])
            if len(scores) > 10:
                formatted += " ..."
            self.lbl_scores.setText(tr("match.scores", scores=formatted))
        else:
            self.lbl_scores.setText(tr("match.scores_none"))

    def _update_result_viewer(self, result: dict) -> None:
        # Show the search image in the result viewer
        if self._search_array is not None:
            self.result_viewer.load_from_array(self._search_array)
            self.result_viewer.clear_overlays()

            # Draw match locations — handle both "locations" and "boxes" keys
            locations = result.get("locations") or result.get("boxes") or []
            scores = result.get("scores", [])
            # Each location is (x, y) or (x, y, w, h) in pixel coords
            for i, loc in enumerate(locations):
                score = scores[i] if i < len(scores) else 0.0
                if isinstance(loc, (list, tuple)):
                    if len(loc) >= 4:
                        x, y, w, h = loc[:4]
                        self.result_viewer.add_rect(
                            x, y, x + w, y + h,
                            color="lime",
                            label=f"{score:.3f}" if score else "",
                        )
                    elif len(loc) >= 2:
                        x, y = loc[:2]
                        self.result_viewer.add_point(
                            x, y,
                            color="red",
                            radius=5,
                            label=f"{score:.3f}" if score else "",
                        )

    def _update_heatmap(self, result: dict) -> None:
        heatmap = result.get("heatmap") or result.get("correlation_map")
        if heatmap is None:
            return
        self._heatmap_data = np.asarray(heatmap)

        # Create or reuse FigureCanvas
        if self._heatmap_canvas is None:
            self._heatmap_figure = Figure(figsize=(4, 3), dpi=100)
            self._heatmap_canvas = FigureCanvasQTAgg(self._heatmap_figure)

            # Replace placeholder in grid
            grid = self.heatmap_placeholder.parent().layout()
            if isinstance(grid, QGridLayout):
                idx = grid.indexOf(self.heatmap_placeholder)
                if idx >= 0:
                    row, col, rs, cs = grid.getItemPosition(idx)
                    grid.removeWidget(self.heatmap_placeholder)
                    self.heatmap_placeholder.hide()
                    grid.addWidget(self._heatmap_canvas, row, col, rs, cs)

        self._heatmap_figure.clear()
        ax = self._heatmap_figure.add_subplot(111)
        ax.imshow(self._heatmap_data, cmap="hot", aspect="auto")
        ax.set_title(tr("match.heatmap_title"))
        self._heatmap_figure.tight_layout()
        self._heatmap_canvas.draw()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return serialisable state for project save."""
        return {
            "template_paths": list(self._template_paths),
            "search_path": self._search_path,
            "match_threshold": self.threshold_spin.value(),
            "nms_threshold": self.nms_spin.value(),
        }

    def set_state(self, state: dict) -> None:
        """Restore tab state from a loaded project."""
        if not state:
            return

        self.threshold_spin.setValue(
            float(state.get("match_threshold", DEFAULT_MATCH_THRESHOLD))
        )
        self.nms_spin.setValue(
            float(state.get("nms_threshold", DEFAULT_NMS_THRESHOLD))
        )

        search_path = state.get("search_path", "")
        if search_path:
            arr = self._service.load_image(search_path)
            if arr is not None:
                self._search_path = search_path
                self._search_array = arr
                import os
                self.search_path_label.setText(os.path.basename(search_path))
                self.search_viewer.load_from_array(arr)

        template_paths = state.get("template_paths", [])
        for p in template_paths:
            arr = self._service.load_image(p)
            if arr is None:
                continue
            self._template_paths.append(p)
            self._template_arrays.append(arr)
            item = QTreeWidgetItem()
            item.setText(0, p.split("/")[-1].split("\\")[-1])
            item.setText(1, f"{arr.shape[1]}x{arr.shape[0]}")
            item.setData(0, Qt.ItemDataRole.UserRole, p)
            self.template_tree.addTopLevelItem(item)
            self.template_viewer.load_from_array(arr)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        # Group boxes
        self._template_card.setTitle(tr("match.templates"))
        self._search_card.setTitle(tr("match.search_image"))
        self._parameter_card.setTitle(tr("match.parameters"))
        self._operation_card.setTitle(tr("match.operations"))
        self._statistics_card.setTitle(tr("match.statistics"))

        # Tree headers
        self.template_tree.setHeaderLabels([
            tr("match.template_name"), tr("match.template_size")
        ])

        # Buttons
        self.btn_add_template.setText(tr("match.add_template"))
        self.btn_remove_template.setText(tr("match.remove_template"))
        self.btn_clear_templates.setText(tr("match.clear_templates"))
        self.btn_load_search.setText(tr("match.load_search"))
        self.btn_single_match.setText(tr("match.single_match"))
        self.btn_single_multi.setText(tr("match.single_multi_match"))
        self.btn_multi_target.setText(tr("match.multi_target_match"))

        # Parameter labels
        self._threshold_label.setText(tr("match.threshold"))
        self._nms_label.setText(tr("match.nms_threshold"))

        # Viewer labels
        self._template_viewer_label.setText(tr("match.template_viewer"))
        self._search_viewer_label.setText(tr("match.search_viewer"))
        self._result_viewer_label.setText(tr("match.result_viewer"))
        self._heatmap_label.setText(tr("match.heatmap"))

        # Dynamic labels — best effort
        self.heatmap_placeholder.setText(tr("match.heatmap_placeholder"))
        if self.search_path_label.text() != tr("match.no_search_loaded"):
            pass  # path was set by user action, keep it

        # Heatmap title (re-set if heatmap exists)
        if self._heatmap_figure is not None:
            for ax in self._heatmap_figure.axes:
                ax.set_title(tr("match.heatmap_title"))
            self._heatmap_canvas.draw()
