"""Service locator — single entry point for all application services.

Each service is lazily created on first access via @property.
Services receive `self` (AppContext) so they can reach each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .batch_service import BatchService
    from .detection_service import DetectionService
    from .feature_service import FeatureService
    from .image_processing_service import ImageProcessingService
    from .license_service import LicenseService
    from .matching_service import MatchingService
    from .plugin_service import PluginService
    from .project_service import ProjectService
    from .raster_service import RasterService
    from .report_service import ReportService
    from .resource_service import ResourceService
    from .scene_service import SceneService
    from .vector_service import VectorService


class AppContext:
    """Service locator singleton for the migration application layer."""

    __slots__ = ("_svc",)

    def __init__(self) -> None:
        object.__setattr__(self, "_svc", {})

    def _get(self, key: str, factory: Callable[[], Any]) -> Any:
        svc: dict = self._svc
        if key not in svc:
            svc[key] = factory()
        return svc[key]

    # -- services ----------------------------------------------------------

    @property
    def project_service(self) -> ProjectService:
        from .project_service import ProjectService
        return self._get("project", lambda: ProjectService(self))

    @property
    def resource_service(self) -> ResourceService:
        from .resource_service import ResourceService
        return self._get("resource", lambda: ResourceService(self))

    @property
    def report_service(self) -> ReportService:
        from .report_service import ReportService
        return self._get("report", lambda: ReportService(self))

    @property
    def raster_service(self) -> RasterService:
        from .raster_service import RasterService
        return self._get("raster", lambda: RasterService(self))

    @property
    def vector_service(self) -> VectorService:
        from .vector_service import VectorService
        return self._get("vector", lambda: VectorService(self))

    @property
    def detection_service(self) -> DetectionService:
        from .detection_service import DetectionService
        return self._get("detection", lambda: DetectionService(self))

    @property
    def matching_service(self) -> MatchingService:
        from .matching_service import MatchingService
        return self._get("matching", lambda: MatchingService(self))

    @property
    def batch_service(self) -> BatchService:
        from .batch_service import BatchService
        return self._get("batch", lambda: BatchService(self))

    @property
    def plugin_service(self) -> PluginService:
        from .plugin_service import PluginService
        return self._get("plugin", lambda: PluginService(self))

    @property
    def license_service(self) -> LicenseService:
        from .license_service import LicenseService
        return self._get("license", lambda: LicenseService(self))

    @property
    def image_processing_service(self) -> ImageProcessingService:
        from .image_processing_service import ImageProcessingService
        return self._get("image_processing", lambda: ImageProcessingService(self))

    @property
    def feature_service(self) -> FeatureService:
        from .feature_service import FeatureService
        return self._get("feature", lambda: FeatureService(self))

    @property
    def scene_service(self) -> SceneService:
        from .scene_service import SceneService
        return self._get("scene", lambda: SceneService(self))
