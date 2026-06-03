# ui/__init__.py
from .main_window import MainWindow
from .feature_tab import FeatureTab
from .match_tab import MatchTab  # 确保导出MatchTab
from .vector_tab import VectorTab

__all__ = ["MainWindow", "FeatureTab", "MatchTab", "VectorTab"]