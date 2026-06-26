"""Object detection orchestration -- wraps core.detection and core.model_registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from core.detection import ONNXDetector, DetectionOutput
from core.model_registry import ModelConfig, ModelRegistry, infer_model_config

if TYPE_CHECKING:
    from .app_context import AppContext


class DetectionService:
    """Orchestrates ONNX-based object detection."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._detector = ONNXDetector()
        self._registry = ModelRegistry()

    # -- model management ------------------------------------------------------

    def list_models(self) -> dict[str, ModelConfig]:
        return self._registry.load_all()

    def get_model_config(self, model_path: str) -> ModelConfig | None:
        return self._registry.get(model_path)

    def save_model_config(self, config: ModelConfig) -> None:
        self._registry.save(config)

    def infer_config(self, model_path: str, confidence: float = 0.5,
                     iou_threshold: float = 0.45) -> ModelConfig:
        return infer_model_config(model_path, confidence, iou_threshold)

    # -- detection -------------------------------------------------------------

    def load_model(self, model_path: str) -> bool:
        return self._detector.load_model(model_path)

    def apply_config(self, config: ModelConfig) -> None:
        self._detector.apply_model_config(config)

    def set_classes(self, names: dict[int, str]) -> None:
        self._detector.set_classes(names)

    def detect(self, image: np.ndarray) -> DetectionOutput:
        return self._detector.detect(image)

    def draw(self, image: np.ndarray, output: DetectionOutput,
             color: tuple[int, int, int] = (0, 255, 0)) -> np.ndarray:
        return self._detector.draw_detections(image, output, color)

    @property
    def available(self) -> bool:
        return self._detector.available
