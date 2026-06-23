"""3D viewer toolbar — measurement, section, annotation commands."""

from __future__ import annotations

from typing import Optional

import numpy as np

from common.logger import logger


class MeasurementTool:
    """Interactive distance / area measurement for the 3D viewer.

    Placed points are stored; distance is displayed as a LineSet overlay.
    """

    def __init__(self):
        self._points: list[np.ndarray] = []
        self._active = False
        self._total_distance: float = 0.0
        self._closed: bool = False  # True = area measurement

    @property
    def active(self) -> bool:
        return self._active

    def start(self, closed: bool = False) -> None:
        self._points.clear()
        self._total_distance = 0.0
        self._closed = closed
        self._active = True
        logger.debug("Measurement tool started")

    def add_point(self, pt: np.ndarray) -> None:
        if not self._active:
            return
        self._points.append(pt.copy())
        if len(self._points) >= 2:
            delta = pt - self._points[-2]
            self._total_distance += float(np.linalg.norm(delta))

    def finish(self) -> tuple[float, float | None]:
        """Returns (distance, area_or_None)."""
        self._active = False
        if self._closed and len(self._points) >= 3:
            area = self._compute_polygon_area()
            self._points.clear()
            return self._total_distance, area
        self._points.clear()
        return self._total_distance, None

    def cancel(self) -> None:
        self._active = False
        self._points.clear()
        self._total_distance = 0.0

    def get_last_points(self, n: int = 2) -> list[np.ndarray]:
        return self._points[-n:] if len(self._points) >= n else self._points[:]

    @property
    def segment_labels(self) -> list[str]:
        labels = []
        for i in range(1, len(self._points)):
            d = float(np.linalg.norm(self._points[i] - self._points[i - 1]))
            labels.append(f"{d:.2f} m")
        if self._closed and len(self._points) >= 3:
            d = float(np.linalg.norm(self._points[-1] - self._points[0]))
            labels.append(f"{d:.2f} m")
        return labels

    def _compute_polygon_area(self) -> float:
        pts_2d = np.array(self._points)[:, :2]
        n = len(pts_2d)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts_2d[i][0] * pts_2d[j][1]
            area -= pts_2d[j][0] * pts_2d[i][1]
        return abs(area) / 2.0


class SectionTool:
    """Profile / cross-section extraction tool.

    Draw a line across the scene; extract elevation profile along that line.
    """

    def __init__(self):
        self._start: Optional[np.ndarray] = None
        self._end: Optional[np.ndarray] = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def start(self, pt: np.ndarray) -> None:
        self._start = pt.copy()
        self._end = None
        self._active = True

    def update(self, pt: np.ndarray) -> None:
        if self._active:
            self._end = pt.copy()

    def finish(self) -> tuple[np.ndarray, np.ndarray] | None:
        self._active = False
        if self._start is not None and self._end is not None:
            return self._start.copy(), self._end.copy()
        return None

    def cancel(self) -> None:
        self._active = False
        self._start = None
        self._end = None

    def sample_profile(
        self, dem: np.ndarray, num_samples: int = 100
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample elevation along the section line on a DEM.

        Returns (distances, elevations) arrays.
        """
        if self._start is None or self._end is None:
            return np.array([]), np.array([])

        t = np.linspace(0, 1, num_samples)
        line_pts = self._start + np.outer(t, self._end - self._start)

        x_idx = np.clip((line_pts[:, 0] / 1.0).astype(int), 0, dem.shape[1] - 1)
        y_idx = np.clip((line_pts[:, 1] / 1.0).astype(int), 0, dem.shape[0] - 1)
        elevations = dem[y_idx, x_idx]

        dists = np.zeros(num_samples)
        for i in range(1, num_samples):
            dists[i] = dists[i - 1] + float(np.linalg.norm(line_pts[i] - line_pts[i - 1]))

        return dists, elevations


class AnnotationTool:
    """3D text annotation placement."""

    def __init__(self):
        self._annotations: list[dict] = []

    def add(
        self, position: np.ndarray, text: str, color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ) -> str:
        aid = f"anno_{len(self._annotations)}"
        self._annotations.append(
            {
                "id": aid,
                "position": position.tolist(),
                "text": text,
                "color": color,
            }
        )
        return aid

    def remove(self, annotation_id: str) -> bool:
        for i, a in enumerate(self._annotations):
            if a["id"] == annotation_id:
                self._annotations.pop(i)
                return True
        return False

    def clear(self) -> None:
        self._annotations.clear()

    @property
    def all(self) -> list[dict]:
        return list(self._annotations)
