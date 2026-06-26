"""Welcome workspace with action buttons and recent projects."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from common.version import APP_VERSION


class WelcomeWorkspace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recent_projects: list[str] = []

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Hero section
        hero = QFrame()
        hero.setObjectName("WelcomeHero")
        hero.setFixedWidth(520)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(40, 40, 40, 32)
        hero_layout.setSpacing(12)

        self.title_label = QLabel()
        self.title_label.setObjectName("AppTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("MutedText")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)

        hero_layout.addWidget(self.title_label)
        hero_layout.addWidget(self.subtitle_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.new_btn = QPushButton()
        self.new_btn.setObjectName("PrimaryButton")
        self.new_btn.setMinimumWidth(160)
        self.new_btn.setMinimumHeight(40)

        self.open_btn = QPushButton()
        self.open_btn.setMinimumWidth(160)
        self.open_btn.setMinimumHeight(40)

        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.open_btn)
        hero_layout.addLayout(btn_row)

        # Recent projects
        self.recent_label = QLabel()
        self.recent_label.setObjectName("SectionTitle")
        hero_layout.addSpacing(8)
        hero_layout.addWidget(self.recent_label)

        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(150)
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        hero_layout.addWidget(self.recent_list)

        layout.addWidget(hero, alignment=Qt.AlignmentFlag.AlignCenter)
        self.retranslate_ui()

    def set_recent_projects(self, paths: list[str]) -> None:
        self._recent_projects = paths
        self.recent_list.clear()
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.recent_list.addItem(item)
        if not paths:
            self.recent_list.addItem(tr("welcome.no_recent"))

    def _on_recent_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            window = self.window()
            if hasattr(window, "open_project_path"):
                window.open_project_path(path)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app.title"))
        self.subtitle_label.setText(
            tr("welcome.subtitle", version=APP_VERSION)
        )
        self.new_btn.setText(tr("action.new_project"))
        self.open_btn.setText(tr("action.open_project"))
        self.recent_label.setText(tr("welcome.recent"))
