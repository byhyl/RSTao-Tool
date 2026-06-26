"""Feature detection service -- wraps core.feature_detection.FeatureDetection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from core.feature_detection import FeatureDetection

if TYPE_CHECKING:
    from .app_context import AppContext


class FeatureService:
    """Orchestrates feature detection operations."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._detector = FeatureDetection()

    def harris(self, gray: np.ndarray, k: float = 0.04,
               threshold: float = 0.01) -> tuple[np.ndarray, int]:
        return self._detector.harris_detect(gray, k, threshold)

    def moravec(self, gray: np.ndarray,
                threshold: float = 0.01) -> tuple[np.ndarray, int]:
        return self._detector.moravec_detect(gray, threshold)

    def forstner(self, gray: np.ndarray,
                 threshold: float = 0.01) -> tuple[np.ndarray, int]:
        return self._detector.forstner_detect(gray, threshold)

    def susan(self, gray: np.ndarray, t: float = 27.0,
              threshold: float = 0.01) -> tuple[np.ndarray, int]:
        return self._detector.susan_detect(gray, t, threshold)

    def draw_points(self, img: np.ndarray, mask: np.ndarray,
                    point_size: int = 3) -> np.ndarray:
        return self._detector.draw_points(img, mask, point_size)

    def rotate(self, img: np.ndarray, angle: float, scale: float = 1.0,
               method: str = "bilinear") -> np.ndarray:
        return self._detector.rotate_image(img, angle, scale, method)

    def load_image(self, path: str) -> np.ndarray | None:
        return self._detector.load_image(path)

    def save_image(self, img: np.ndarray, path: str) -> None:
        self._detector.save_image(img, path)
