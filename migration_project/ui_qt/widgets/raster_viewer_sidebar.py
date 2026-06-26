"""Compact side panel for RasterViewer: band/mode/brightness/coordinate/zoom controls.

Usage:
    sidebar = RasterViewerSidebar()
    sidebar.attach(viewer)          # connect to a RasterViewer
    layout.addWidget(sidebar)       # embed next to the viewer
    sidebar.detach()                # disconnect when switching tabs
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr


_DEBOUNCE_MS = 150


class RasterViewerSidebar(QWidget):
    """Control panel that attaches to a RasterViewer."""

    def __init__(self, viewer=None, parent=None):
        super().__init__(parent)
        self._viewer = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._apply_stretch)

        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        self._setup_ui()

        if viewer is not None:
            self.attach(viewer)

    # -- public API -----------------------------------------------------------

    def attach(self, viewer) -> None:
        """Connect to a RasterViewer; disconnect any previous one first."""
        self.detach()
        self._viewer = viewer
        # Sync UI from viewer state
        self._sync_from_viewer()
        # Connect signals
        viewer.cursorMoved.connect(self._on_cursor_moved)
        viewer.viewChanged.connect(self._on_view_changed)
        viewer.displayParamsChanged.connect(self._sync_from_viewer)
        self._set_enabled(True)

    def detach(self) -> None:
        """Disconnect from the current viewer."""
        if self._viewer is None:
            return
        try:
            self._viewer.cursorMoved.disconnect(self._on_cursor_moved)
        except (RuntimeError, TypeError):
            pass
        try:
            self._viewer.viewChanged.disconnect(self._on_view_changed)
        except (RuntimeError, TypeError):
            pass
        try:
            self._viewer.displayParamsChanged.disconnect(self._sync_from_viewer)
        except (RuntimeError, TypeError):
            pass
        self._viewer = None
        self._set_enabled(False)

    def viewer(self):
        return self._viewer

    def retranslate_ui(self) -> None:
        """Refresh translatable strings (call after language change)."""
        self._band_group.setTitle(tr("raster.sidebar.band_selection"))
        self._mode_group.setTitle(tr("raster.sidebar.display_mode"))
        self._stretch_group.setTitle(tr("raster.sidebar.brightness_contrast"))
        self._coord_group.setTitle(tr("raster.sidebar.coordinates"))
        self._view_group.setTitle(tr("raster.sidebar.view_controls"))
        self._lbl_r.setText(tr("raster.sidebar.band_r"))
        self._lbl_g.setText(tr("raster.sidebar.band_g"))
        self._lbl_b.setText(tr("raster.sidebar.band_b"))
        self._radio_rgb.setText(tr("raster.sidebar.mode_rgb"))
        self._radio_gray.setText(tr("raster.sidebar.mode_grayscale"))
        self._lbl_low.setText(tr("raster.sidebar.stretch_low"))
        self._lbl_high.setText(tr("raster.sidebar.stretch_high"))
        self._btn_auto.setText(tr("raster.sidebar.stretch_auto"))
        self._lbl_pixel_prefix.setText(tr("raster.sidebar.pixel_coord"))
        self._lbl_geo_prefix.setText(tr("raster.sidebar.geo_coord"))
        self._btn_fit.setText(tr("raster.sidebar.fit"))
        self._btn_actual.setText(tr("raster.sidebar.zoom_actual"))
        self._btn_zoom_in.setText(tr("raster.sidebar.zoom_in"))
        self._btn_zoom_out.setText(tr("raster.sidebar.zoom_out"))
        self._btn_screenshot.setText(tr("raster.sidebar.screenshot"))

    # -- UI construction -------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Band selection
        self._band_group = QGroupBox(tr("raster.sidebar.band_selection"))
        band_form = QVBoxLayout(self._band_group)

        row_r = QHBoxLayout()
        self._lbl_r = QLabel(tr("raster.sidebar.band_r"))
        self._combo_r = QComboBox()
        self._combo_r.setMinimumWidth(60)
        row_r.addWidget(self._lbl_r)
        row_r.addWidget(self._combo_r, 1)
        band_form.addLayout(row_r)

        row_g = QHBoxLayout()
        self._lbl_g = QLabel(tr("raster.sidebar.band_g"))
        self._combo_g = QComboBox()
        self._combo_g.setMinimumWidth(60)
        row_g.addWidget(self._lbl_g)
        row_g.addWidget(self._combo_g, 1)
        band_form.addLayout(row_g)

        row_b = QHBoxLayout()
        self._lbl_b = QLabel(tr("raster.sidebar.band_b"))
        self._combo_b = QComboBox()
        self._combo_b.setMinimumWidth(60)
        row_b.addWidget(self._lbl_b)
        row_b.addWidget(self._combo_b, 1)
        band_form.addLayout(row_b)

        layout.addWidget(self._band_group)

        # Display mode
        self._mode_group = QGroupBox(tr("raster.sidebar.display_mode"))
        mode_layout = QHBoxLayout(self._mode_group)
        self._radio_rgb = QRadioButton(tr("raster.sidebar.mode_rgb"))
        self._radio_gray = QRadioButton(tr("raster.sidebar.mode_grayscale"))
        self._radio_rgb.setChecked(True)
        mode_layout.addWidget(self._radio_rgb)
        mode_layout.addWidget(self._radio_gray)
        layout.addWidget(self._mode_group)

        # Brightness / contrast
        self._stretch_group = QGroupBox(tr("raster.sidebar.brightness_contrast"))
        stretch_layout = QVBoxLayout(self._stretch_group)

        row_low = QHBoxLayout()
        self._lbl_low = QLabel(tr("raster.sidebar.stretch_low"))
        self._slider_low = QSlider(Qt.Orientation.Horizontal)
        self._slider_low.setRange(0, 100)
        self._slider_low.setValue(2)
        self._spin_low = QSpinBox()
        self._spin_low.setRange(0, 100)
        self._spin_low.setValue(2)
        row_low.addWidget(self._lbl_low)
        row_low.addWidget(self._slider_low, 1)
        row_low.addWidget(self._spin_low)
        stretch_layout.addLayout(row_low)

        row_high = QHBoxLayout()
        self._lbl_high = QLabel(tr("raster.sidebar.stretch_high"))
        self._slider_high = QSlider(Qt.Orientation.Horizontal)
        self._slider_high.setRange(0, 100)
        self._slider_high.setValue(98)
        self._spin_high = QSpinBox()
        self._spin_high.setRange(0, 100)
        self._spin_high.setValue(98)
        row_high.addWidget(self._lbl_high)
        row_high.addWidget(self._slider_high, 1)
        row_high.addWidget(self._spin_high)
        stretch_layout.addLayout(row_high)

        self._btn_auto = QPushButton(tr("raster.sidebar.stretch_auto"))
        stretch_layout.addWidget(self._btn_auto)
        layout.addWidget(self._stretch_group)

        # Coordinates
        self._coord_group = QGroupBox(tr("raster.sidebar.coordinates"))
        coord_layout = QVBoxLayout(self._coord_group)
        row_px = QHBoxLayout()
        self._lbl_pixel_prefix = QLabel(tr("raster.sidebar.pixel_coord"))
        self._lbl_pixel = QLabel("(0, 0)")
        row_px.addWidget(self._lbl_pixel_prefix)
        row_px.addWidget(self._lbl_pixel, 1)
        coord_layout.addLayout(row_px)
        row_geo = QHBoxLayout()
        self._lbl_geo_prefix = QLabel(tr("raster.sidebar.geo_coord"))
        self._lbl_geo = QLabel("(0.0000, 0.0000)")
        row_geo.addWidget(self._lbl_geo_prefix)
        row_geo.addWidget(self._lbl_geo, 1)
        coord_layout.addLayout(row_geo)
        layout.addWidget(self._coord_group)

        # View controls
        self._view_group = QGroupBox(tr("raster.sidebar.view_controls"))
        view_layout = QVBoxLayout(self._view_group)

        zoom_row = QHBoxLayout()
        self._btn_fit = QPushButton(tr("raster.sidebar.fit"))
        self._btn_actual = QPushButton(tr("raster.sidebar.zoom_actual"))
        self._btn_zoom_in = QPushButton(tr("raster.sidebar.zoom_in"))
        self._btn_zoom_out = QPushButton(tr("raster.sidebar.zoom_out"))
        zoom_row.addWidget(self._btn_fit)
        zoom_row.addWidget(self._btn_actual)
        zoom_row.addWidget(self._btn_zoom_in)
        zoom_row.addWidget(self._btn_zoom_out)
        view_layout.addLayout(zoom_row)

        self._lbl_zoom_pct = QLabel("100%")
        self._lbl_zoom_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_layout.addWidget(self._lbl_zoom_pct)

        self._btn_screenshot = QPushButton(tr("raster.sidebar.screenshot"))
        view_layout.addWidget(self._btn_screenshot)
        layout.addWidget(self._view_group)

        layout.addStretch()

        # Wire internal signals
        self._wire_signals()
        self._set_enabled(False)

    def _wire_signals(self) -> None:
        # Band combos
        self._combo_r.currentIndexChanged.connect(self._on_band_changed)
        self._combo_g.currentIndexChanged.connect(self._on_band_changed)
        self._combo_b.currentIndexChanged.connect(self._on_band_changed)

        # Display mode
        self._radio_rgb.toggled.connect(lambda checked: checked and self._on_mode_changed())
        self._radio_gray.toggled.connect(lambda checked: checked and self._on_mode_changed())

        # Stretch sliders/spin
        self._slider_low.valueChanged.connect(self._spin_low.setValue)
        self._spin_low.valueChanged.connect(self._slider_low.setValue)
        self._slider_low.valueChanged.connect(self._schedule_stretch)
        self._slider_high.valueChanged.connect(self._spin_high.setValue)
        self._spin_high.valueChanged.connect(self._slider_high.setValue)
        self._slider_high.valueChanged.connect(self._schedule_stretch)
        self._btn_auto.clicked.connect(self._on_stretch_auto)

        # View buttons (delegate to viewer)
        self._btn_fit.clicked.connect(self._on_fit)
        self._btn_actual.clicked.connect(self._on_zoom_actual)
        self._btn_zoom_in.clicked.connect(self._on_zoom_in)
        self._btn_zoom_out.clicked.connect(self._on_zoom_out)
        self._btn_screenshot.clicked.connect(self._on_screenshot)

    # -- internal slots --------------------------------------------------------

    def _on_band_changed(self) -> None:
        if self._viewer is None:
            return
        r = self._combo_r.currentData() or self._combo_r.currentText()
        g = self._combo_g.currentData() or self._combo_g.currentText()
        b = self._combo_b.currentData() or self._combo_b.currentText()
        try:
            indices = [int(r), int(g), int(b)]
            self._viewer.set_band_indices(indices)
        except (ValueError, TypeError):
            pass

    def _on_mode_changed(self) -> None:
        if self._viewer is None:
            return
        mode = "grayscale" if self._radio_gray.isChecked() else "rgb"
        self._viewer.set_display_mode(mode)
        # Toggle band dropdowns visibility
        is_gray = mode == "grayscale"
        self._lbl_g.setVisible(not is_gray)
        self._combo_g.setVisible(not is_gray)
        self._lbl_b.setVisible(not is_gray)
        self._combo_b.setVisible(not is_gray)
        if is_gray:
            self._lbl_r.setText(tr("raster.sidebar.band_single"))
        else:
            self._lbl_r.setText(tr("raster.sidebar.band_r"))

    def _schedule_stretch(self) -> None:
        self._debounce_timer.start(_DEBOUNCE_MS)

    def _apply_stretch(self) -> None:
        if self._viewer is None:
            return
        self._viewer.set_percentile_stretch(
            self._slider_low.value(), self._slider_high.value()
        )

    def _on_stretch_auto(self) -> None:
        self._slider_low.setValue(2)
        self._slider_high.setValue(98)
        if self._viewer is not None:
            self._viewer.set_percentile_stretch(2.0, 98.0)

    def _on_fit(self) -> None:
        if self._viewer:
            self._viewer.fit_to_view()

    def _on_zoom_actual(self) -> None:
        if self._viewer:
            self._viewer.zoom_actual()

    def _on_zoom_in(self) -> None:
        if self._viewer:
            self._viewer.zoom_by(1.25)

    def _on_zoom_out(self) -> None:
        if self._viewer:
            self._viewer.zoom_by(0.8)

    def _on_screenshot(self) -> None:
        if self._viewer:
            self._viewer.export_screenshot()

    def _on_cursor_moved(self, px: int, py: int, geo_x: float, geo_y: float) -> None:
        self._lbl_pixel.setText(f"({px}, {py})")
        self._lbl_geo.setText(f"({geo_x:.6f}, {geo_y:.6f})")

    def _on_view_changed(self, zoom: float, _ox: float, _oy: float) -> None:
        self._lbl_zoom_pct.setText(f"{zoom*100:.0f}%")

    # -- sync / state ----------------------------------------------------------

    def _sync_from_viewer(self) -> None:
        """Pull display state from the viewer into the UI controls."""
        if self._viewer is None:
            return
        # Band count determines combobox range
        n_bands = self._viewer.raw_band_count
        if n_bands <= 1:
            self._band_group.setVisible(False)
        else:
            self._band_group.setVisible(True)
            self._populate_band_combos(n_bands)

        # Band indices
        indices = self._viewer.band_indices
        if len(indices) >= 1:
            self._combo_r.setCurrentIndex(indices[0] - 1)
        if len(indices) >= 2:
            self._combo_g.setCurrentIndex(indices[1] - 1)
        if len(indices) >= 3:
            self._combo_b.setCurrentIndex(indices[2] - 1)

        # Display mode
        mode = self._viewer.display_mode
        if mode == "grayscale":
            self._radio_gray.setChecked(True)
        else:
            self._radio_rgb.setChecked(True)
        self._on_mode_changed()  # update band row visibility

        # Stretch
        low, high = self._viewer.percentile_stretch
        self._slider_low.blockSignals(True)
        self._spin_low.blockSignals(True)
        self._slider_low.setValue(int(low))
        self._spin_low.setValue(int(low))
        self._slider_low.blockSignals(False)
        self._spin_low.blockSignals(False)
        self._slider_high.setValue(int(high))
        self._spin_high.setValue(int(high))

    def _populate_band_combos(self, n_bands: int) -> None:
        for combo in (self._combo_r, self._combo_g, self._combo_b):
            if combo.count() == n_bands:
                continue
            combo.blockSignals(True)
            combo.clear()
            for i in range(1, n_bands + 1):
                combo.addItem(str(i), i)
            combo.blockSignals(False)

    def _set_enabled(self, enabled: bool) -> None:
        self._band_group.setEnabled(enabled)
        self._mode_group.setEnabled(enabled)
        self._stretch_group.setEnabled(enabled)
        self._view_group.setEnabled(enabled)
        if not enabled:
            self._lbl_pixel.setText("(0, 0)")
            self._lbl_geo.setText("(0.0000, 0.0000)")
            self._lbl_zoom_pct.setText("100%")
