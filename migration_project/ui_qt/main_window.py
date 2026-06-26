"""Main Qt workbench window for the migration project."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from application import AppContext
from common.app_icon import resolve_app_icon_path
from common.logger import logger
from common.version import APP_VERSION
from .docks.layer_dock import LayerDock
from .docks.log_dock import LogDock
from .docks.project_dock import ProjectDock
from .docks.properties_dock import PropertiesDock
from .docks.task_dock import TaskDock
from .i18n import current_language, set_language, tr
from .theme import AVAILABLE_THEMES, DEFAULT_THEME, load_stylesheet
from .workspaces.project_workspace import ProjectWorkspace
from .workspaces.welcome_workspace import WelcomeWorkspace


class MainWindow(QMainWindow):

    TAB_NAMES = [
        "feature",
        "image_processing",
        "match",
        "detection",
        "vector",
        "viewer_3d",
    ]

    def __init__(self):
        super().__init__()
        self._ctx = AppContext()
        self.current_theme = DEFAULT_THEME
        self._tabs: dict[str, object] = {}
        self._tab_actions: dict[str, QAction] = {}
        self._cursor_connections: list = []
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self._apply_window_icon()
        self._apply_theme(self.current_theme)

        self.workspace_stack = QStackedWidget()
        self.welcome_workspace = WelcomeWorkspace()
        self.project_workspace = ProjectWorkspace()
        self.workspace_stack.addWidget(self.welcome_workspace)
        self.workspace_stack.addWidget(self.project_workspace)

        # Add all functional tabs to the stack (lazy: placeholder pages)
        self._tab_indices: dict[str, int] = {
            "welcome": 0,
            "project": 1,
        }
        self._init_tabs()

        self.setCentralWidget(self.workspace_stack)

        self._create_actions()
        self._create_menu_bar()
        self._create_docks()
        self._create_status_bar()
        self._connect_signals()
        self._refresh_project_views()
        self.log_dock.append(tr("log.initialized"))

    def _init_tabs(self) -> None:
        """Lazy-init tab placeholders. Real widgets created on first switch."""
        for name in self.TAB_NAMES:
            placeholder = self.workspace_stack.addWidget(
                _TabPlaceholder(tr(f"tab.{name}"))
            )
            self._tab_indices[name] = placeholder

    def _ensure_tab(self, name: str) -> object | None:
        """Create the real tab widget on first access, injecting AppContext."""
        if name in self._tabs:
            return self._tabs[name]

        tab = None
        try:
            if name == "image_processing":
                from .tabs.image_processing_tab import ImageProcessingTab
                tab = ImageProcessingTab()
                tab.setup(self._ctx)
            elif name == "feature":
                from .tabs.feature_tab import FeatureTab
                tab = FeatureTab(self._ctx)
            elif name == "match":
                from .tabs.match_tab import MatchTab
                tab = MatchTab()
            elif name == "detection":
                from .tabs.detection_tab import DetectionTab
                tab = DetectionTab()
            elif name == "vector":
                from .tabs.vector_tab import VectorTab
                tab = VectorTab()
                tab._ctx = self._ctx
            elif name == "viewer_3d":
                from .tabs.viewer_3d_tab import Viewer3DTab
                tab = Viewer3DTab(self._ctx)
        except ImportError as exc:
            logger.warning("无法加载 tab '%s': %s", name, exc)
            return None

        if tab is not None:
            # Wire statusMessage to status bar
            if hasattr(tab, "statusMessage"):
                tab.statusMessage.connect(
                    lambda msg: self.statusBar().showMessage(msg, 5000)
                )
            idx = self._tab_indices.get(name)
            if idx is not None:
                old_widget = self.workspace_stack.widget(idx)
                self.workspace_stack.removeWidget(old_widget)
                if old_widget:
                    old_widget.deleteLater()
                self.workspace_stack.insertWidget(idx, tab)
                self._tab_indices[name] = idx
            self._tabs[name] = tab
        return tab

    def switch_panel(self, name: str) -> None:
        """Switch to a named workspace or tab."""
        self._disconnect_viewer_cursors()

        # Ensure tab is loaded if it's a functional tab
        if name in self.TAB_NAMES:
            tab = self._ensure_tab(name)
            if tab is None:
                return
            if hasattr(tab, "on_show"):
                tab.on_show()

        if name == "project":
            widget = self.project_workspace
            self.workspace_stack.setCurrentWidget(widget)
        elif name in self._tab_indices:
            widget = self.workspace_stack.widget(self._tab_indices[name])
            if widget:
                self.workspace_stack.setCurrentWidget(widget)
        else:
            widget = self.welcome_workspace
            self.workspace_stack.setCurrentWidget(widget)

        # Connect cursor moved signal for viewer tabs
        self._connect_viewer_cursors(widget)

    def open_project_path(self, path: str) -> None:
        """Open a project by its file path (used by recent-projects click)."""
        project = self._ctx.project_service.load_project(path)
        if not project:
            QMessageBox.warning(
                self, tr("dialog.open_project.title"), tr("dialog.warning.open_failed")
            )
            return
        self._refresh_project_views()
        self._show_status(tr("status.project_opened", name=Path(path).name))
        self.log_dock.append(tr("log.project_opened", path=path))

    def _apply_window_icon(self) -> None:
        icon_path = resolve_app_icon_path()
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(icon_path)))

    def _create_actions(self) -> None:
        self.action_new = QAction(self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_new.triggered.connect(self.new_project)

        self.action_open = QAction(self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_project)

        self.action_save = QAction(self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_project)

        self.action_save_as = QAction(self)
        self.action_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.action_save_as.triggered.connect(self.save_project_as)

        self.action_import_resource = QAction(self)
        self.action_import_resource.setShortcut(QKeySequence("Ctrl+I"))
        self.action_import_resource.triggered.connect(self.import_resource)

        self.action_exit = QAction(self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)

        self.action_about = QAction(self)
        self.action_about.triggered.connect(self.show_about)

        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.action_language_zh = QAction(self)
        self.action_language_zh.setCheckable(True)
        self.action_language_zh.triggered.connect(lambda: self.change_language("zh"))
        self.language_group.addAction(self.action_language_zh)
        self.action_language_en = QAction(self)
        self.action_language_en.setCheckable(True)
        self.action_language_en.triggered.connect(lambda: self.change_language("en"))
        self.language_group.addAction(self.action_language_en)

        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.action_theme_light = QAction(self)
        self.action_theme_light.setCheckable(True)
        self.action_theme_light.triggered.connect(lambda: self.change_theme("light"))
        self.theme_group.addAction(self.action_theme_light)
        self.action_theme_dark = QAction(self)
        self.action_theme_dark.setCheckable(True)
        self.action_theme_dark.triggered.connect(lambda: self.change_theme("dark"))
        self.theme_group.addAction(self.action_theme_dark)

        self._retranslate_actions()

    def _create_menu_bar(self) -> None:
        self.menuBar().clear()

        self.file_menu = self.menuBar().addMenu("")
        self.file_menu.addAction(self.action_new)
        self.file_menu.addAction(self.action_open)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_save)
        self.file_menu.addAction(self.action_save_as)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_import_resource)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_exit)

        # Functions menu with tab entries
        self.functions_menu = self.menuBar().addMenu("")
        self._tab_actions.clear()
        for name in self.TAB_NAMES:
            action = QAction(tr(f"tab.{name}"), self)
            action.triggered.connect(lambda checked, n=name: self.switch_panel(n))
            self.functions_menu.addAction(action)
            self._tab_actions[name] = action

        self.view_menu = self.menuBar().addMenu("")
        self._dock_view_menu = self.view_menu
        self.theme_menu = self.view_menu.addMenu("")
        self.theme_menu.addAction(self.action_theme_light)
        self.theme_menu.addAction(self.action_theme_dark)
        self.view_menu.addSeparator()

        self.tools_menu = self.menuBar().addMenu("")
        self.tools_menu.addAction(self.action_import_resource)

        self.language_menu = self.menuBar().addMenu("")
        self.language_menu.addAction(self.action_language_zh)
        self.language_menu.addAction(self.action_language_en)

        self.help_menu = self.menuBar().addMenu("")
        self.help_menu.addAction(self.action_about)
        self._retranslate_menu_bar()

    def _create_docks(self) -> None:
        self.project_dock = ProjectDock()
        self.layer_dock = LayerDock()
        self.properties_dock = PropertiesDock()
        self.task_dock = TaskDock()
        self.log_dock = LogDock()

        self.docks: dict[str, QDockWidget] = {}
        self._add_dock("dock.project", self.project_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("dock.layers", self.layer_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("dock.properties", self.properties_dock, Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("dock.tasks", self.task_dock, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("dock.log", self.log_dock, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(self.docks["dock.tasks"], self.docks["dock.log"])
        self._retranslate_docks()

    def _add_dock(self, key: str, widget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(self)
        dock.setObjectName(key)
        dock.setWidget(widget)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.addDockWidget(area, dock)
        self._dock_view_menu.addAction(dock.toggleViewAction())
        self.docks[key] = dock
        return dock

    def _create_status_bar(self) -> None:
        self.statusBar().showMessage(tr("status.ready"))

    def _connect_signals(self) -> None:
        self.welcome_workspace.new_btn.clicked.connect(self.new_project)
        self.welcome_workspace.open_btn.clicked.connect(self.open_project)

    # -- cursor coordinate display ---------------------------------------------

    def _connect_viewer_cursors(self, widget: QWidget) -> None:
        """Find all RasterViewers in the widget and connect cursorMoved to status bar."""
        from .widgets.raster_viewer import RasterViewer
        for viewer in widget.findChildren(RasterViewer):
            conn = viewer.cursorMoved.connect(self._on_viewer_cursor_update)
            self._cursor_connections.append(conn)

    def _disconnect_viewer_cursors(self) -> None:
        """Disconnect previously connected cursorMoved signals."""
        from PySide6.QtCore import QObject
        for conn in self._cursor_connections:
            try:
                QObject.disconnect(conn)
            except Exception:
                pass
        self._cursor_connections.clear()

    def _on_viewer_cursor_update(self, px: int, py: int, geo_x: float, geo_y: float) -> None:
        self.statusBar().showMessage(
            tr("raster.cursor_coords", px=px, py=py, geo_x=geo_x, geo_y=geo_y)
        )

    # -- project operations --------------------------------------------------

    def new_project(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("dialog.new_project.title"), tr("dialog.new_project.name")
        )
        if not ok or not name.strip():
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_project.title"),
            f"{name.strip()}.rstao",
            tr("filter.project"),
        )
        if not path:
            return

        if self._ctx.project_service.new_project(name.strip(), path):
            self._refresh_project_views()
            self._show_status(tr("status.project_created", name=Path(path).name))
            self.log_dock.append(tr("log.project_created", path=path))
        else:
            QMessageBox.warning(
                self, tr("dialog.new_project.title"), tr("dialog.warning.create_failed")
            )

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.open_project.title"),
            "",
            tr("filter.project_all"),
        )
        if not path:
            return
        self.open_project_path(path)

    def save_project(self) -> None:
        if not self._ctx.project_service.current_project:
            self.save_project_as()
            return
        if self._ctx.project_service.save_project():
            self._refresh_project_views()
            self._show_status(tr("status.project_saved"))
            self.log_dock.append(tr("log.project_saved"))
        else:
            QMessageBox.warning(
                self, tr("dialog.save_project.title"), tr("dialog.warning.save_failed")
            )

    def save_project_as(self) -> None:
        if not self._ctx.project_service.current_project:
            QMessageBox.information(
                self, tr("dialog.save_project.title"), tr("dialog.warning.need_project")
            )
            return
        current_name = self._ctx.project_service.current_project.get(
            "project_name", tr("project.untitled")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_project_as.title"),
            f"{current_name}.rstao",
            tr("filter.project"),
        )
        if not path:
            return
        if self._ctx.project_service.save_project_as(current_name, path):
            self._ctx.project_service.add_recent_project(path)
            self._refresh_project_views()
            self._show_status(tr("status.project_saved_as", name=Path(path).name))
            self.log_dock.append(tr("log.project_saved_as", path=path))
        else:
            QMessageBox.warning(
                self, tr("dialog.save_project_as.title"), tr("dialog.warning.save_failed")
            )

    def import_resource(self) -> None:
        if not self._ctx.project_service.current_project:
            QMessageBox.information(
                self, tr("dialog.import_resource.title"), tr("dialog.warning.need_project")
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.import_resource.title"),
            "",
            tr("filter.resources"),
        )
        if not path:
            return
        try:
            self._ctx.resource_service.import_resource(path)
            self._ctx.project_service.save_project()
        except Exception as exc:
            logger.exception("Qt resource import failed")
            QMessageBox.warning(
                self,
                tr("dialog.import_resource.title"),
                tr("dialog.warning.import_failed", error=exc),
            )
            return

        self._refresh_project_views()
        self._show_status(tr("status.resource_imported", name=Path(path).name))
        self.log_dock.append(tr("log.resource_imported", path=path))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            tr("dialog.about.title"),
            tr("dialog.about.body", version=APP_VERSION),
        )

    def _refresh_project_views(self) -> None:
        project = self._ctx.project_service.current_project
        project_path = self._ctx.project_service.project_path
        recent = self._ctx.project_service.get_recent_projects() or []

        self.project_dock.set_project(project, project_path)
        self.layer_dock.set_project(project)
        self.properties_dock.show_project(project, project_path)
        self.task_dock.set_project(project)
        self.project_workspace.show_project(project, project_path)
        self.welcome_workspace.set_recent_projects(recent)

        if project:
            self.workspace_stack.setCurrentWidget(self.project_workspace)
        else:
            self.workspace_stack.setCurrentWidget(self.welcome_workspace)
        self._update_window_title(project)

    def _show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def change_language(self, language: str) -> None:
        if not set_language(language):
            return
        self._retranslate_ui()
        self.log_dock.append(tr(f"log.language_changed.{current_language()}"))

    def change_theme(self, theme_name: str) -> None:
        if theme_name not in AVAILABLE_THEMES:
            return
        self.current_theme = theme_name
        self._apply_theme(theme_name)
        self._retranslate_actions()
        self._show_status(tr(f"status.theme_changed.{theme_name}"))

    def _apply_theme(self, theme_name: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(load_stylesheet(theme_name))

    def _retranslate_ui(self) -> None:
        self._retranslate_actions()
        self._retranslate_menu_bar()
        self._retranslate_docks()
        self.welcome_workspace.retranslate_ui()
        self.project_workspace.retranslate_ui()
        self.project_dock.retranslate_ui()
        self.layer_dock.retranslate_ui()
        self.properties_dock.retranslate_ui()
        self.task_dock.retranslate_ui()
        self._update_window_title(self._ctx.project_service.current_project)
        self.statusBar().showMessage(tr("status.ready"))
        # Propagate to loaded tabs
        for tab in self._tabs.values():
            if hasattr(tab, "retranslate_ui"):
                tab.retranslate_ui()

    def _retranslate_actions(self) -> None:
        self.action_new.setText(tr("action.new_project"))
        self.action_open.setText(tr("action.open_project"))
        self.action_save.setText(tr("action.save_project"))
        self.action_save_as.setText(tr("action.save_project_as"))
        self.action_import_resource.setText(tr("action.import_resource"))
        self.action_exit.setText(tr("action.exit"))
        self.action_about.setText(tr("action.about"))
        self.action_language_zh.setText(tr("language.zh"))
        self.action_language_en.setText(tr("language.en"))
        self.action_language_zh.setChecked(current_language() == "zh")
        self.action_language_en.setChecked(current_language() == "en")
        self.action_theme_light.setText(tr("theme.light"))
        self.action_theme_dark.setText(tr("theme.dark"))
        self.action_theme_light.setChecked(self.current_theme == "light")
        self.action_theme_dark.setChecked(self.current_theme == "dark")

        # Tab menu entries
        for name in self.TAB_NAMES:
            if name in self._tab_actions:
                self._tab_actions[name].setText(tr(f"tab.{name}"))

    def _retranslate_menu_bar(self) -> None:
        self.file_menu.setTitle(tr("menu.file"))
        self.functions_menu.setTitle(tr("menu.functions"))
        self.view_menu.setTitle(tr("menu.view"))
        self.theme_menu.setTitle(tr("menu.theme"))
        self.tools_menu.setTitle(tr("menu.tools"))
        self.language_menu.setTitle(tr("menu.language"))
        self.help_menu.setTitle(tr("menu.help"))

    def _retranslate_docks(self) -> None:
        for key, dock in self.docks.items():
            dock.setWindowTitle(tr(key))

    def _update_window_title(self, project: dict | None) -> None:
        app_title = tr("app.title")
        if project:
            name = project.get("project_name", tr("project.untitled"))
            self.setWindowTitle(f"{name} - {app_title} {APP_VERSION}")
        else:
            self.setWindowTitle(f"{app_title} {APP_VERSION}")


class _TabPlaceholder(QWidget):
    """Simple placeholder shown before a tab is first loaded."""
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QLabel, QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(name)
        label.setStyleSheet("color: #666; font-size: 18px;")
        layout.addWidget(label)
