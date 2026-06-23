"""Background task helpers for the 3D viewer."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from inspect import Parameter, signature
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class Viewer3DTaskResult(Generic[T]):
    """Result object returned to the Tk main thread."""

    name: str
    value: Optional[T] = None
    error: Optional[BaseException] = None
    cancelled: bool = False
    elapsed_ms: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Viewer3DTaskProgress:
    """Progress event emitted from a background 3D task."""

    name: str
    value: float
    text: str = ""
    stage: str = ""


class Viewer3DTask:
    """Small cancellable worker wrapper used by Viewer3DTab."""

    def __init__(
        self,
        name: str,
        worker: Callable[..., T],
        on_done: Callable[[Viewer3DTaskResult[T]], None],
        on_progress: Callable[[Viewer3DTaskProgress], None] | None = None,
    ):
        self.name = name
        self._worker = worker
        self._on_done = on_done
        self._on_progress = on_progress
        self._cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._worker_accepts_progress = self._accepts_progress(worker)

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    def report_progress(self, value: float, text: str = "", stage: str = "") -> None:
        if self._on_progress is None:
            return
        try:
            event = Viewer3DTaskProgress(
                name=self.name,
                value=max(0.0, min(1.0, float(value))),
                text=text,
                stage=stage,
            )
            self._on_progress(event)
        except Exception:
            pass

    def _run(self) -> None:
        started = time.perf_counter()
        result: Viewer3DTaskResult[T]
        try:
            self.report_progress(0.02, f"{self.name}: 准备数据", "prepare")
            if self._worker_accepts_progress:
                value = self._worker(self._cancel_event, self.report_progress)
            else:
                value = self._worker(self._cancel_event)
            result = Viewer3DTaskResult(
                name=self.name,
                value=value,
                cancelled=self._cancel_event.is_set(),
            )
        except BaseException as exc:
            result = Viewer3DTaskResult(name=self.name, error=exc)
        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._on_done(result)

    @staticmethod
    def _accepts_progress(worker: Callable[..., T]) -> bool:
        try:
            params = list(signature(worker).parameters.values())
        except (TypeError, ValueError):
            return False
        positional = [
            p
            for p in params
            if p.kind
            in (
                Parameter.POSITIONAL_ONLY,
                Parameter.POSITIONAL_OR_KEYWORD,
                Parameter.VAR_POSITIONAL,
            )
        ]
        return any(p.kind == Parameter.VAR_POSITIONAL for p in positional) or len(positional) >= 2


def benchmark_points(name: str, point_count: int, started: float) -> dict[str, float]:
    """Return simple throughput metrics for 3D processing operations."""
    elapsed_ms = max((time.perf_counter() - started) * 1000.0, 1e-9)
    return {
        f"{name}_elapsed_ms": elapsed_ms,
        f"{name}_points": float(point_count),
        f"{name}_points_per_sec": float(point_count) / (elapsed_ms / 1000.0),
    }
