"""Object detection domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BoundingBox:
    """Normalized bounding box with classification."""

    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    confidence: float = 0.0
    class_id: int = 0
    class_name: str = ""

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict:
        return {
            "x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2,
            "confidence": self.confidence, "class_id": self.class_id,
            "class_name": self.class_name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BoundingBox:
        return cls(
            x1=d.get("x1", 0.0), y1=d.get("y1", 0.0),
            x2=d.get("x2", 0.0), y2=d.get("y2", 0.0),
            confidence=d.get("confidence", 0.0), class_id=d.get("class_id", 0),
            class_name=d.get("class_name", ""),
        )


@dataclass
class DetectionModel:
    """Configuration for an object detection model."""

    path: str = ""
    name: str = ""
    input_size: tuple[int, int] = (640, 640)
    class_names: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.45
    color_order: str = "BGR"
    normalization: str = "0-1"
    letterbox: bool = False
    output_format: str = "auto"

    def to_dict(self) -> dict:
        return {
            "path": self.path, "name": self.name,
            "input_size": list(self.input_size),
            "class_names": self.class_names,
            "confidence_threshold": self.confidence_threshold,
            "iou_threshold": self.iou_threshold,
            "color_order": self.color_order,
            "normalization": self.normalization,
            "letterbox": self.letterbox,
            "output_format": self.output_format,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DetectionModel:
        input_size = d.get("input_size", [640, 640])
        if isinstance(input_size, list) and len(input_size) >= 2:
            input_size = (int(input_size[0]), int(input_size[1]))
        else:
            input_size = (640, 640)
        return cls(
            path=d.get("path", ""), name=d.get("name", ""),
            input_size=input_size,
            class_names=d.get("class_names", []),
            confidence_threshold=d.get("confidence_threshold", 0.5),
            iou_threshold=d.get("iou_threshold", 0.45),
            color_order=d.get("color_order", "BGR"),
            normalization=d.get("normalization", "0-1"),
            letterbox=d.get("letterbox", False),
            output_format=d.get("output_format", "auto"),
        )


@dataclass
class DetectionRequest:
    """Input for a detection operation.

    image is typed Any because domain layer cannot import numpy.
    Implementation layers enforce np.ndarray at runtime.
    """

    image: Any = None
    model: Optional[DetectionModel] = None

    def to_dict(self) -> dict:
        return {
            "model": self.model.to_dict() if self.model else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DetectionRequest:
        model_d = d.get("model")
        return cls(
            model=DetectionModel.from_dict(model_d) if isinstance(model_d, dict) else None,
        )


@dataclass
class DetectionResult:
    """Output of a detection operation."""

    detections: list[BoundingBox] = field(default_factory=list)
    inference_time_ms: float = 0.0
    image_size: tuple[int, int] = (0, 0)

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def has_detections(self) -> bool:
        return len(self.detections) > 0

    def to_dict(self) -> dict:
        return {
            "detections": [d.to_dict() for d in self.detections],
            "inference_time_ms": self.inference_time_ms,
            "image_size": list(self.image_size),
        }

    @classmethod
    def from_dict(cls, d: dict) -> DetectionResult:
        img_size = d.get("image_size", [0, 0])
        if isinstance(img_size, list) and len(img_size) >= 2:
            img_size = (int(img_size[0]), int(img_size[1]))
        else:
            img_size = (0, 0)
        return cls(
            detections=[BoundingBox.from_dict(b) for b in d.get("detections", [])],
            inference_time_ms=d.get("inference_time_ms", 0.0),
            image_size=img_size,
        )
