"""Core package exports.

The package keeps compatibility exports lazy so importing one submodule does not
pull optional dependencies from unrelated features.
"""

from importlib import import_module

_EXPORTS = {
    "BatchProcessor": ".batch_processor",
    "BatchResult": ".batch_processor",
    "BatchTask": ".batch_processor",
    "CHINA_EPSG": ".coordinate_system",
    "COMMON_EPSG": ".coordinate_system",
    "CoordinateSystem": ".coordinate_system",
    "CoordinateTransform": ".coordinate_system",
    "DetectionOutput": ".detection",
    "DetectionResult": ".detection",
    "ONNXDetector": ".detection",
    "FeatureDetection": ".feature_detection",
    "ImageProcessingCore": ".image_processing",
    "OperatorSpec": ".image_processing",
    "ParameterSpec": ".image_processing",
    "ProcessingResult": ".image_processing",
    "match_histogram": ".image_processing",
    "ImageMatchingCore": ".image_matching",
    "draw_heatmap": ".image_matching",
    "draw_matches": ".image_matching",
    "ncc_match": ".image_matching",
    "nms": ".image_matching",
    "BasePlugin": ".plugin_manager",
    "PluginInfo": ".plugin_manager",
    "PluginManager": ".plugin_manager",
    "FeatureStats": ".report_generator",
    "MatchStats": ".report_generator",
    "ReportGenerator": ".report_generator",
    "create_resource_record": ".resource_manager",
    "read_scene_preview": ".resource_manager",
    "resource_summary": ".resource_manager",
    "resource_type_label": ".resource_manager",
    "add_property_field": ".vector_processing",
    "batch_update_properties": ".vector_processing",
    "create_line_feature": ".vector_processing",
    "create_new_layer": ".vector_processing",
    "create_point_feature": ".vector_processing",
    "create_polygon_feature": ".vector_processing",
    "delete_property_field": ".vector_processing",
    "invalidate_shapely_cache": ".vector_processing",
    "move_feature": ".vector_processing",
    "select_feature": ".vector_processing",
    "update_feature_property": ".vector_processing",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
