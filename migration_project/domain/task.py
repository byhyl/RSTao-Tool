"""Task history and batch result domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskRecord:
    """A single task execution record for the project audit trail.

    Merges fields from core/result_history.py::ResultRecord and
    core/batch_processor.py::BatchTask.
    """

    task_id: str = ""
    category: str = ""
    title: str = ""
    status: str = "done"
    created_at: str = ""
    duration_ms: float = 0.0
    result_path: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    input_hashes: dict[str, str] = field(default_factory=dict)
    spatial_refs: list[str] = field(default_factory=list)
    model_config: dict[str, Any] = field(default_factory=dict)
    software_version: str = "RSTao-Tool"
    notes: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == "done"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "category": self.category,
            "title": self.title, "status": self.status,
            "created_at": self.created_at, "duration_ms": self.duration_ms,
            "result_path": self.result_path, "params": self.params,
            "inputs": self.inputs, "outputs": self.outputs,
            "metrics": self.metrics, "data_sources": self.data_sources,
            "input_hashes": self.input_hashes, "spatial_refs": self.spatial_refs,
            "model_config": self.model_config, "software_version": self.software_version,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskRecord:
        return cls(
            task_id=d.get("task_id", ""), category=d.get("category", ""),
            title=d.get("title", ""), status=d.get("status", "done"),
            created_at=d.get("created_at", ""), duration_ms=d.get("duration_ms", 0.0),
            result_path=d.get("result_path", ""), params=d.get("params", {}),
            inputs=d.get("inputs", []), outputs=d.get("outputs", []),
            metrics=d.get("metrics", {}), data_sources=d.get("data_sources", []),
            input_hashes=d.get("input_hashes", {}), spatial_refs=d.get("spatial_refs", []),
            model_config=d.get("model_config", {}),
            software_version=d.get("software_version", "RSTao-Tool"),
            notes=d.get("notes", ""),
        )


@dataclass
class TaskHistory:
    """Collection of task records with summary statistics."""

    records: list[TaskRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.records if r.is_success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.records if r.is_failed)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total * 100 if self.total else 0.0

    def to_dict(self) -> dict:
        return {"records": [r.to_dict() for r in self.records]}

    @classmethod
    def from_dict(cls, d: dict) -> TaskHistory:
        return cls(records=[TaskRecord.from_dict(r) for r in d.get("records", [])])
