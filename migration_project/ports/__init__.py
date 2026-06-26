"""Abstract interfaces (ports) for the RSTao-Tool migration.

These are pure ABCs -- no implementations, no imports from core/ or data/.
(Except PluginInfo which is already a pure dataclass in core/.)
"""

from __future__ import annotations

from .detector import Detector
from .image_reader import ImageReader
from .image_writer import ImageWriter
from .license_provider import LicenseProvider
from .plugin_host import PluginHost
from .project_repository import ProjectRepository
from .vector_reader import VectorReader

__all__ = [
    "Detector",
    "ImageReader",
    "ImageWriter",
    "LicenseProvider",
    "PluginHost",
    "ProjectRepository",
    "VectorReader",
]
