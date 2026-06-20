"""UI package exports.

GUI modules depend on CustomTkinter and other desktop-only packages, so they are
loaded lazily to keep non-GUI imports testable.
"""

from importlib import import_module

_EXPORTS = {
    "BatchDialog": ".batch_dialog",
    "CoordinateTab": ".coordinate_tab",
    "DetectionTab": ".detection_tab",
    "FeatureTab": ".feature_tab",
    "MainWindow": ".main_window",
    "MatchTab": ".match_tab",
    "PluginDialog": ".plugin_dialog",
    "SettingsTab": ".settings_tab",
    "VectorTab": ".vector_tab",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
