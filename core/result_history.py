"""Result history helpers for project-level audit trails."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class ResultRecord:
    """A user-visible record of an analysis/export result."""

    category: str
    title: str
    status: str = "done"
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def make_result_record(category: str, title: str, **kwargs) -> Dict[str, Any]:
    """Create a JSON-serializable result history record."""
    return ResultRecord(category=category, title=title, **kwargs).to_dict()
