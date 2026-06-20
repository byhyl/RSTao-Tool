"""Data package exports with lazy optional vector dependencies."""

from importlib import import_module

_EXPORTS = {
    "get_geotiff_info": ".image_io",
    "get_image_metadata": ".image_io",
    "read_geotiff_with_geo": ".image_io",
    "read_image": ".image_io",
    "save_image": ".image_io",
    "read_shp": ".vector_io",
    "save_shp": ".vector_io",
    "save_dwg": ".vector_io",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
