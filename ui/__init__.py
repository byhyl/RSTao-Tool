# ui/__init__.py
from .batch_dialog import BatchDialog
from .coordinate_tab import CoordinateTab
from .detection_tab import DetectionTab
from .feature_tab import FeatureTab
from .main_window import MainWindow
from .match_tab import MatchTab  # 确保导出 MatchTab
from .plugin_dialog import PluginDialog
from .settings_tab import SettingsTab
from .vector_tab import VectorTab

__all__ = [
    "MainWindow",
    "FeatureTab",
    "MatchTab",
    "VectorTab",
    "SettingsTab",
    "BatchDialog",
    "CoordinateTab",
    "DetectionTab",
    "PluginDialog",
]
