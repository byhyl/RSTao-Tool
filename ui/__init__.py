# ui/__init__.py
from .feature_tab import FeatureTab
from .main_window import MainWindow
from .match_tab import MatchTab  # 纭繚瀵煎嚭MatchTab
from .vector_tab import VectorTab
from .settings_tab import SettingsTab
from .batch_dialog import BatchDialog
from .coordinate_tab import CoordinateTab
from .detection_tab import DetectionTab
from .plugin_dialog import PluginDialog

__all__ = ["MainWindow", "FeatureTab", "MatchTab", "VectorTab", "SettingsTab", "BatchDialog", "CoordinateTab", "DetectionTab", "PluginDialog"]
