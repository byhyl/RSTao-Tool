"""Image processing tab — operator pipeline with side-by-side raster preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..task_runner import run_background
from ..widgets.raster_viewer import RasterViewer


class ImageProcessingTab(QWidget):
    """Image processing tab with operator pipeline and side-by-side raster preview.

    Layout:
        Left panel (QScrollArea):
          - Data management: load image / load reference / clear buttons
          - Operator selector: category QComboBox + operator QComboBox
          - Dynamic parameter card (QFormLayout rebuilt from OperatorSpec)
          - Action card: Run button + metrics display (QTextEdit)

        Right panel:
          - QSplitter with two RasterViewer instances (original / result)
          - Help button (opens non-modal operator documentation dialog)
          - Save result button
    """

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Backend context — set externally via setup()
        self._ctx: Any = None
        self._image_processing_service: Any = None

        # State
        self._image_path: str | None = None
        self._orig_array: np.ndarray | None = None
        self._ref_array: np.ndarray | None = None
        self._result_array: np.ndarray | None = None
        self._current_operator_id: str | None = None
        self._current_params: dict[str, Any] = {}
        self._param_widgets: dict[str, QWidget] = {}
        self._metrics_text: str = ""
        self._help_dialog: QDialog | None = None

        # Build the UI
        self._build_ui()

    def setup(self, ctx: Any) -> None:
        """Wire up the AppContext so this tab can reach services."""
        self._ctx = ctx
        self._image_processing_service = ctx.image_processing_service
        self._populate_categories()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- left panel -------------------------------------------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(320)
        left_scroll.setMaximumWidth(460)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        left_layout.addWidget(self._build_data_card())
        left_layout.addWidget(self._build_operator_card())
        left_layout.addWidget(self._build_param_card())
        left_layout.addWidget(self._build_action_card())
        left_layout.addStretch(1)

        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)

        # -- right panel ------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        self._orig_viewer = RasterViewer()
        self._result_viewer = RasterViewer()

        viewer_split = QSplitter(Qt.Orientation.Horizontal)
        viewer_split.addWidget(self._orig_viewer)
        viewer_split.addWidget(self._result_viewer)
        viewer_split.setSizes([500, 500])
        right_layout.addWidget(viewer_split, 1)

        # Bottom button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._help_btn = QPushButton()
        self._help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(self._help_btn)

        btn_row.addStretch()

        self._save_btn = QPushButton()
        self._save_btn.clicked.connect(self._save_result)
        btn_row.addWidget(self._save_btn)

        right_layout.addLayout(btn_row)

        splitter.addWidget(right_widget)
        splitter.setSizes([360, 900])
        outer.addWidget(splitter)

        self.retranslate_ui()

    # ------------------------------------------------------------------
    # Card builders
    # ------------------------------------------------------------------

    def _build_data_card(self) -> QGroupBox:
        group = QGroupBox()

        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._load_image_btn = QPushButton()
        self._load_image_btn.clicked.connect(self._on_load_image)
        btn_row.addWidget(self._load_image_btn)

        self._load_ref_btn = QPushButton()
        self._load_ref_btn.clicked.connect(self._on_load_reference)
        btn_row.addWidget(self._load_ref_btn)

        self._clear_btn = QPushButton()
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._clear_btn)

        layout.addLayout(btn_row)

        self._image_path_label = QLabel()
        self._image_path_label.setWordWrap(True)
        layout.addWidget(self._image_path_label)

        self._data_group = group
        return group

    def _build_operator_card(self) -> QGroupBox:
        group = QGroupBox()
        layout = QFormLayout(group)
        layout.setSpacing(8)

        self._category_combo = QComboBox()
        self._category_combo.currentTextChanged.connect(self._on_category_changed)
        layout.addRow("", self._category_combo)

        self._operator_combo = QComboBox()
        self._operator_combo.currentTextChanged.connect(self._on_operator_changed)
        layout.addRow("", self._operator_combo)

        self._operator_description = QLabel()
        self._operator_description.setWordWrap(True)
        layout.addRow("", self._operator_description)

        self._operator_group = group
        return group

    def _build_param_card(self) -> QGroupBox:
        group = QGroupBox()
        self._param_layout = QFormLayout(group)
        self._param_layout.setSpacing(8)
        self._param_layout.setContentsMargins(0, 8, 0, 0)

        self._param_empty_label = QLabel()
        self._param_layout.addRow(self._param_empty_label)

        self._param_group = group
        return group

    def _build_action_card(self) -> QGroupBox:
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._run_btn = QPushButton()
        self._run_btn.setMinimumHeight(36)
        self._run_btn.clicked.connect(self._on_run)
        layout.addWidget(self._run_btn)

        self._metrics_edit = QTextEdit()
        self._metrics_edit.setReadOnly(True)
        self._metrics_edit.setMaximumHeight(100)
        layout.addWidget(self._metrics_edit)

        self._action_group = group
        return group

    # ------------------------------------------------------------------
    # Retranslate
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all translatable strings."""
        self._data_group.setTitle(tr("tab.image_processing.data"))
        self._load_image_btn.setText(tr("tab.image_processing.load_image"))
        self._load_ref_btn.setText(tr("tab.image_processing.load_reference"))
        self._clear_btn.setText(tr("tab.image_processing.clear"))
        self._operator_group.setTitle(tr("tab.image_processing.operator"))
        self._param_group.setTitle(tr("tab.image_processing.parameters"))
        self._param_empty_label.setText(tr("tab.image_processing.no_operator_selected"))
        self._action_group.setTitle(tr("tab.image_processing.actions"))
        self._run_btn.setText(tr("tab.image_processing.run"))
        self._help_btn.setText(tr("tab.image_processing.help"))
        self._save_btn.setText(tr("tab.image_processing.save_result"))

    # ------------------------------------------------------------------
    # Data management slots
    # ------------------------------------------------------------------

    def _on_load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("tab.image_processing.load_image_title"),
            "",
            tr("tab.image_processing.image_filter"),
        )
        if not path:
            return

        self._image_path = path
        try:
            self._orig_array = _read_image_as_array(path)
            self._orig_viewer.load_from_array(self._orig_array)
            self._image_path_label.setText(Path(path).name)
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.load_error_title"),
                tr("tab.image_processing.load_error", error=str(exc)),
            )

    def _on_load_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("tab.image_processing.load_reference_title"),
            "",
            tr("tab.image_processing.image_filter"),
        )
        if not path:
            return

        try:
            self._ref_array = _read_image_as_array(path)
            # Reference image is shown in the result viewer temporarily
            # or could be overlaid — here we just store it.
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.load_error_title"),
                tr("tab.image_processing.load_error", error=str(exc)),
            )

    def _on_clear(self) -> None:
        self._image_path = None
        self._orig_array = None
        self._ref_array = None
        self._result_array = None
        self._metrics_text = ""

        self._orig_viewer.clear_image()
        self._result_viewer.clear_image()
        self._image_path_label.clear()
        self._metrics_edit.clear()

    # ------------------------------------------------------------------
    # Operator selection slots
    # ------------------------------------------------------------------

    def _populate_categories(self) -> None:
        if self._image_processing_service is None:
            return

        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem(tr("tab.image_processing.all_categories"), "")
        for cat in self._image_processing_service.list_categories():
            self._category_combo.addItem(cat, cat)
        self._category_combo.blockSignals(False)

        # Populate operators for initial (all) selection
        self._populate_operators()

    def _populate_operators(self, category: str | None = None) -> None:
        if self._image_processing_service is None:
            return

        self._operator_combo.blockSignals(True)
        self._operator_combo.clear()

        ops = self._image_processing_service.list_operators(category)
        for op in ops:
            self._operator_combo.addItem(op.name, op.id)

        self._operator_combo.blockSignals(False)

        # If operators exist, select first and rebuild params
        if ops:
            self._on_operator_changed()
        else:
            self._clear_parameters()

    def _on_category_changed(self) -> None:
        cat = self._category_combo.currentData() or None
        self._populate_operators(cat)

    def _on_operator_changed(self) -> None:
        idx = self._operator_combo.currentIndex()
        if idx < 0:
            self._clear_parameters()
            return

        op_id = self._operator_combo.currentData()
        if not op_id:
            self._clear_parameters()
            return

        self._current_operator_id = op_id
        spec = self._image_processing_service.get_operator(op_id)
        if spec is None:
            self._clear_parameters()
            return

        self._operator_description.setText(spec.description or "")
        self._build_parameter_widgets(spec)

    def _clear_parameters(self) -> None:
        """Clear all parameter widgets from the form layout."""
        self._current_operator_id = None
        self._current_params = {}
        self._param_widgets.clear()

        # Remove all rows from the layout
        while self._param_layout.rowCount() > 0:
            self._param_layout.removeRow(self._param_layout.rowCount() - 1)
        # Re-add the empty label
        self._param_layout.addRow(self._param_empty_label)
        self._param_empty_label.setVisible(True)

    def _build_parameter_widgets(self, spec: Any) -> None:
        """Rebuild the QFormLayout from an OperatorSpec.parameters list."""
        self._clear_parameters()
        self._param_empty_label.setVisible(False)

        params = getattr(spec, "parameters", None) or []

        for param in params:
            param_name = getattr(param, "name", "")
            param_type = getattr(param, "kind", "string")  # ParameterSpec uses 'kind'
            default = getattr(param, "default", None)
            param_label = getattr(param, "label", "") or param_name
            options = getattr(param, "options", None)
            min_val = getattr(param, "min", None)
            max_val = getattr(param, "max", None)

            if param_type in ("int", "float"):
                widget, reader = _make_numeric_widget(param_type, default, min_val, max_val)
            elif param_type == "bool":
                widget, reader = _make_bool_widget(default)
            elif param_type == "choice" and options:
                widget, reader = _make_choice_widget(options, default)
            else:
                widget, reader = _make_string_widget(default)

            self._param_layout.addRow(param_label, widget)
            self._param_widgets[param_name] = widget

            # Store the reader closure on the widget so we can collect later
            widget._reader = reader  # type: ignore[attr-defined]

    def _collect_params(self) -> dict[str, Any]:
        """Read current values from all parameter widgets."""
        params: dict[str, Any] = {}
        for name, widget in self._param_widgets.items():
            reader = getattr(widget, "_reader", None)
            if reader:
                params[name] = reader()
        return params

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        if self._image_processing_service is None:
            return
        if self._orig_array is None:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.run_error_title"),
                tr("tab.image_processing.no_image_loaded"),
            )
            return
        if self._current_operator_id is None:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.run_error_title"),
                tr("tab.image_processing.no_operator_selected"),
            )
            return

        self._run_btn.setEnabled(False)
        self._metrics_edit.clear()

        params = self._collect_params()
        self._current_params = params

        def _work() -> Any:
            return self._image_processing_service.process(
                self._orig_array, self._current_operator_id, params
            )

        def _on_done(result: Any) -> None:
            self._run_btn.setEnabled(True)
            self._handle_result(result)

        def _on_error(msg: str) -> None:
            self._run_btn.setEnabled(True)
            QMessageBox.warning(
                self,
                tr("tab.image_processing.run_error_title"),
                tr("tab.image_processing.run_error", error=msg),
            )

        run_background(
            _work,
            on_done=_on_done,
            on_error=_on_error,
            parent=self,
        )

    def _handle_result(self, result: Any) -> None:
        """Display the processing result."""
        self._result_array = getattr(result, "image", None)
        metrics = getattr(result, "metrics", None)

        if self._result_array is not None:
            self._result_viewer.load_from_array(self._result_array)

        if metrics is not None:
            if isinstance(metrics, str):
                self._metrics_text = metrics
            elif isinstance(metrics, dict):
                self._metrics_text = "\n".join(
                    f"{k}: {v}" for k, v in metrics.items()
                )
            else:
                self._metrics_text = str(metrics)
            self._metrics_edit.setPlainText(self._metrics_text)

    # ------------------------------------------------------------------
    # Help dialog
    # ------------------------------------------------------------------

    def _show_help(self) -> None:
        if self._current_operator_id is None:
            return
        if self._image_processing_service is None:
            return

        spec = self._image_processing_service.get_operator(self._current_operator_id)
        if spec is None:
            return

        # Reuse existing non-modal dialog if already open
        if self._help_dialog is not None:
            self._help_dialog.raise_()
            self._help_dialog.activateWindow()
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(
            tr("tab.image_processing.help_title", name=getattr(spec, "name", ""))
        )
        dlg.resize(500, 400)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(self._on_help_closed)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)

        body = QTextEdit()
        body.setReadOnly(True)

        help_text = _format_operator_help(spec)
        body.setMarkdown(help_text)
        layout.addWidget(body)

        close_btn = QPushButton(tr("tab.image_processing.close"))
        close_btn.clicked.connect(dlg.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._help_dialog = dlg
        dlg.show()  # non-modal

    def _on_help_closed(self) -> None:
        self._help_dialog = None

    # ------------------------------------------------------------------
    # Save result
    # ------------------------------------------------------------------

    def _save_result(self) -> None:
        if self._result_array is None:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.save_error_title"),
                tr("tab.image_processing.no_result"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("tab.image_processing.save_title"),
            "",
            tr("tab.image_processing.save_filter"),
        )
        if not path:
            return

        try:
            _write_image(path, self._result_array)
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("tab.image_processing.save_error_title"),
                tr("tab.image_processing.save_error", error=str(exc)),
            )

    # ------------------------------------------------------------------
    # Project persistence: get_state / set_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Return a JSON-serializable dict capturing current tab state."""
        return {
            "image_path": self._image_path,
            "operator_id": self._current_operator_id,
            "params": self._current_params,
            "metrics": self._metrics_text,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore tab state from a previously persisted dict."""
        image_path = state.get("image_path")
        if image_path and Path(image_path).is_file():
            try:
                self._image_path = image_path
                self._orig_array = _read_image_as_array(image_path)
                self._orig_viewer.load_from_array(self._orig_array)
                self._image_path_label.setText(Path(image_path).name)
            except Exception:
                pass

        operator_id = state.get("operator_id")
        if operator_id and self._image_processing_service is not None:
            idx = self._operator_combo.findData(operator_id)
            if idx >= 0:
                self._operator_combo.setCurrentIndex(idx)
                # _on_operator_changed already rebuilds params via signal

        params = state.get("params")
        if params:
            self._current_params = params
            for name, value in params.items():
                widget = self._param_widgets.get(name)
                if widget is not None:
                    _apply_param_value(widget, value)

        metrics = state.get("metrics")
        if metrics:
            self._metrics_text = metrics
            self._metrics_edit.setPlainText(metrics)


# ----------------------------------------------------------------------
# Param widget builders
# ----------------------------------------------------------------------

def _make_numeric_widget(
    kind: str, default: Any, min_val: Any, max_val: Any
) -> tuple[QWidget, callable]:
    """Create a QSpinBox/QDoubleSpinBox and a reader closure."""
    if kind == "int":
        w = QSpinBox()
        w.setRange(
            int(min_val) if min_val is not None else -999999,
            int(max_val) if max_val is not None else 999999,
        )
        if default is not None:
            w.setValue(int(default))
    else:
        w = QDoubleSpinBox()
        w.setRange(
            float(min_val) if min_val is not None else -1e9,
            float(max_val) if max_val is not None else 1e9,
        )
        w.setDecimals(4)
        if default is not None:
            w.setValue(float(default))

    def _read() -> Any:
        return w.value()

    return w, _read


def _make_bool_widget(default: Any) -> tuple[QWidget, callable]:
    w = QCheckBox()
    if default is not None:
        w.setChecked(bool(default))

    def _read() -> Any:
        return w.isChecked()

    return w, _read


def _make_choice_widget(
    options: list, default: Any
) -> tuple[QWidget, callable]:
    w = QComboBox()
    for opt in options:
        if isinstance(opt, (tuple, list)) and len(opt) == 2:
            label, value = opt
            w.addItem(str(label), value)
        else:
            w.addItem(str(opt), opt)

    if default is not None:
        idx = w.findData(default)
        if idx >= 0:
            w.setCurrentIndex(idx)

    def _read() -> Any:
        return w.currentData()

    return w, _read


def _make_string_widget(default: Any) -> tuple[QWidget, callable]:
    w = QLineEdit()
    if default is not None:
        w.setText(str(default))

    def _read() -> Any:
        return w.text()

    return w, _read


def _apply_param_value(widget: QWidget, value: Any) -> None:
    """Push a value into a parameter widget based on its type."""
    if isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif hasattr(widget, "setValue"):
        widget.setValue(float(value))
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QComboBox):
        idx = widget.findData(value)
        if idx >= 0:
            widget.setCurrentIndex(idx)
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value))


# ----------------------------------------------------------------------
# I/O helpers
# ----------------------------------------------------------------------

def _read_image_as_array(path: str) -> np.ndarray:
    """Read an image file into a numpy array using common utilities."""
    from data.image_io import read_image

    arr = read_image(str(path))
    if arr is None:
        raise ValueError(f"Cannot read image: {path}")
    return arr


def _write_image(path: str, arr: np.ndarray) -> None:
    """Write a numpy array to disk as an image."""
    from data.image_io import save_image

    save_image(str(path), arr)


def _format_operator_help(spec: Any) -> str:
    """Format an OperatorSpec into Markdown for the help dialog."""
    name = getattr(spec, "name", "") or str(spec.id)
    desc = getattr(spec, "description", "") or tr("tab.image_processing.no_description")

    lines = [
        f"# {name}",
        "",
        desc,
        "",
        "## " + tr("tab.image_processing.parameters"),
        "",
    ]

    params = getattr(spec, "parameters", None) or []
    if params:
        for p in params:
            p_name = getattr(p, "name", "?")
            p_label = getattr(p, "label", "") or p_name
            p_type = getattr(p, "type", "?")
            p_default = getattr(p, "default", None)
            p_desc = getattr(p, "description", "")

            lines.append(f"- **{p_label}** (`{p_name}`)")
            lines.append(f"  - {tr('tab.image_processing.type')}: `{p_type}`")
            if p_default is not None:
                lines.append(f"  - {tr('tab.image_processing.default')}: `{p_default}`")
            if p_desc:
                lines.append(f"  - {p_desc}")
            lines.append("")
    else:
        lines.append(tr("tab.image_processing.no_parameters"))

    return "\n".join(lines)
