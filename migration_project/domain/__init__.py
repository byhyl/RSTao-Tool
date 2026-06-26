"""Domain data contracts for the RSTao-Tool migration.

These are pure dataclasses with no imports from core/, ui/, data/, or application/.
"""

from __future__ import annotations

from .detection import BoundingBox, DetectionModel, DetectionRequest, DetectionResult
from .matching import Match, MatchingRequest, MatchingResult, TemplateImage
from .pointcloud import PointCloudData, PointCloudDataset, PointCloudMetadata
from .project import Project, ProjectResource, ProjectState
from .raster import GeoTransform, RasterBand, RasterDataset, RasterMetadata, SpatialReference
from .resource import Resource, ResourceCatalog, ResourceKind
from .scene import ColorMode, LayerType, SceneGraph, SceneLayer
from .task import TaskHistory, TaskRecord
from .vector import GeometryType, VectorDataset, VectorFeature, VectorGeometry, VectorMetadata

__all__ = [
    "BoundingBox",
    "ColorMode",
    "DetectionModel",
    "DetectionRequest",
    "DetectionResult",
    "GeoTransform",
    "GeometryType",
    "LayerType",
    "Match",
    "MatchingRequest",
    "MatchingResult",
    "PointCloudData",
    "PointCloudDataset",
    "PointCloudMetadata",
    "Project",
    "ProjectResource",
    "ProjectState",
    "RasterBand",
    "RasterDataset",
    "RasterMetadata",
    "Resource",
    "ResourceCatalog",
    "ResourceKind",
    "SceneGraph",
    "SceneLayer",
    "SpatialReference",
    "TaskHistory",
    "TaskRecord",
    "TemplateImage",
    "VectorDataset",
    "VectorFeature",
    "VectorGeometry",
    "VectorMetadata",
]
