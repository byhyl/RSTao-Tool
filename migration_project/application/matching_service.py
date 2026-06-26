"""Image matching orchestration -- wraps core.image_matching.ImageMatchingCore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from core.image_matching import ImageMatchingCore

if TYPE_CHECKING:
    from .app_context import AppContext


class MatchingService:
    """Orchestrates template matching and feature-based matching."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._core = ImageMatchingCore()

    def single_match(self, template: np.ndarray, search: np.ndarray,
                     threshold: float = 0.8) -> dict[str, Any]:
        return self._core.single_matching(template, search, threshold)

    def single_multi_match(self, template: np.ndarray, search: np.ndarray,
                           threshold: float = 0.8,
                           nms_threshold: float = 0.5) -> dict[str, Any]:
        return self._core.single_multi_matching(template, search, threshold, nms_threshold)

    def multi_target_match(self, templates: list[np.ndarray], search: np.ndarray,
                           threshold: float = 0.8) -> dict[str, Any]:
        return self._core.multi_target_matching(templates, search, threshold)

    def load_image(self, path: str) -> np.ndarray | None:
        return self._core.load_image_with_chinese_path(path)

    def save_image(self, img: np.ndarray, path: str) -> None:
        self._core.save_image_with_chinese_path(img, path)
