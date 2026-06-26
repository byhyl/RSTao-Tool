"""Background task runner using QThread for CPU-blocking operations.

Replaces ui/ui_helpers.py::run_background() (threading.Thread + widget.after).
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, QThreadPool, QRunnable


class _TaskWorker(QObject):
    """Worker object that lives on a QThread and runs the target callable."""

    started = Signal()
    progress = Signal(int, int)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, target: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._target = target

    def run(self) -> None:
        self.started.emit()
        try:
            result = self._target()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


def run_background(
    target: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_started: Callable[[], None] | None = None,
    parent: QObject | None = None,
) -> _TaskWorker:
    """Run a blocking function on a background QThread.

    Args:
        target: The blocking function to run (takes no args, returns result).
        on_done: Called on the main thread with the result.
        on_error: Called on the main thread with the error message.
        on_started: Called on the main thread when the task starts.
        parent: Parent QObject for lifecycle management.

    Returns:
        The _TaskWorker instance (caller can keep a reference).
    """
    thread = QThread(parent)
    worker = _TaskWorker(target)
    worker.moveToThread(thread)

    if on_started:
        worker.started.connect(on_started)
    if on_done:
        worker.finished.connect(on_done)
    if on_error:
        worker.error.connect(on_error)

    # Clean up thread when worker finishes
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.started.connect(worker.run)
    thread.finished.connect(thread.deleteLater)
    thread.start()

    return worker


class TaskSignals(QObject):
    """Signals for runnable-based tasks submitted to QThreadPool."""

    started = Signal()
    progress = Signal(int, int)
    finished = Signal(object)
    error = Signal(str)


class TaskRunnable(QRunnable):
    """A QRunnable that emits signals for progress tracking.

    Usage:
        signals = TaskSignals()
        runnable = TaskRunnable(lambda: do_work(), signals)
        QThreadPool.globalInstance().start(runnable)
        signals.finished.connect(on_done)
    """

    def __init__(self, target: Callable[[], Any], signals: TaskSignals):
        super().__init__()
        self._target = target
        self.signals = signals

    def run(self) -> None:
        self.signals.started.emit()
        try:
            result = self._target()
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
