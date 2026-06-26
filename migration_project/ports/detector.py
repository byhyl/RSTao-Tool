"""Abstract interface for object detection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from migration_project.domain.detection import DetectionResult


class Detector(ABC):
    """Port for running object detection.

    Maps to: core/detection.py (ONNXDetector)
    """

    @abstractmethod
    def load_model(self, path: str) -> bool:
        """Load a detection model from disk. Returns True on success."""
        ...

    @abstractmethod
    def detect(self, image: Any) -> DetectionResult:
        """Run detection on an image.

        Args:
            image: np.ndarray (H, W, C) in BGR or RGB format.

        Returns: DetectionResult with bounding boxes and metadata.
        """
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when a model is loaded and ready to detect."""
        ...
