"""Image processing service -- wraps core.image_processing.ImageProcessingCore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from core.image_processing import ImageProcessingCore, OperatorSpec, ProcessingResult

if TYPE_CHECKING:
    from .app_context import AppContext


class ImageProcessingService:
    """Orchestrates image processing operations."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._core = ImageProcessingCore()

    def list_categories(self) -> list[str]:
        """Return list of operator categories."""
        ops = self._core.list_operators()
        seen: set[str] = set()
        result: list[str] = []
        for op in ops:
            if op.category not in seen:
                seen.add(op.category)
                result.append(op.category)
        return result

    def list_operators(self, category: str | None = None) -> list[OperatorSpec]:
        return self._core.list_operators(category)

    def get_operator(self, operator_id: str) -> OperatorSpec | None:
        return self._core.get_operator(operator_id)

    def default_params(self, operator_id: str) -> dict[str, Any]:
        return self._core.default_params(operator_id)

    def process(self, image: np.ndarray, operator_id: str,
                params: dict[str, Any] | None = None) -> ProcessingResult:
        return self._core.process(image, operator_id, params)
