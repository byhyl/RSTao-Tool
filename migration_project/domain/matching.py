"""Image matching / template matching domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TemplateImage:
    """A template image used for matching."""

    path: str = ""
    image: Any = None  # np.ndarray -- transient, not serialized
    name: str = ""

    def to_dict(self) -> dict:
        return {"path": self.path, "name": self.name or self.path}

    @classmethod
    def from_dict(cls, d: dict) -> TemplateImage:
        return cls(path=d.get("path", ""), name=d.get("name", ""))


@dataclass
class MatchingRequest:
    """Input for a template matching operation."""

    templates: list[TemplateImage] = field(default_factory=list)
    search_image: Any = None  # np.ndarray -- transient
    search_path: str = ""
    method: str = "TM_CCOEFF_NORMED"
    threshold: float = 0.8

    def to_dict(self) -> dict:
        return {
            "templates": [t.to_dict() for t in self.templates],
            "search_path": self.search_path,
            "method": self.method,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MatchingRequest:
        return cls(
            templates=[TemplateImage.from_dict(t) for t in d.get("templates", [])],
            search_path=d.get("search_path", ""),
            method=d.get("method", "TM_CCOEFF_NORMED"),
            threshold=d.get("threshold", 0.8),
        )


@dataclass
class Match:
    """A single match result -- maps one template to one location."""

    template: Optional[TemplateImage] = None
    location: tuple[int, int] = (0, 0)
    score: float = 0.0
    bounding_box: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bounding_box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def to_dict(self) -> dict:
        return {
            "template": self.template.to_dict() if self.template else None,
            "location": list(self.location),
            "score": self.score,
            "bounding_box": list(self.bounding_box),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Match:
        loc = d.get("location", [0, 0])
        bbox = d.get("bounding_box", [0, 0, 0, 0])
        tmpl = d.get("template")
        return cls(
            template=TemplateImage.from_dict(tmpl) if isinstance(tmpl, dict) else None,
            location=(int(loc[0]), int(loc[1])) if isinstance(loc, list) and len(loc) >= 2 else (0, 0),
            score=d.get("score", 0.0),
            bounding_box=(
                (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                if isinstance(bbox, list) and len(bbox) >= 4 else (0, 0, 0, 0)
            ),
        )


@dataclass
class MatchingResult:
    """Output of a template matching operation."""

    matches: list[Match] = field(default_factory=list)
    search_path: str = ""
    method: str = ""
    threshold: float = 0.0
    elapsed_ms: float = 0.0
    template_count: int = 0

    @property
    def match_count(self) -> int:
        return len(self.matches)

    @property
    def best_match(self) -> Optional[Match]:
        if not self.matches:
            return None
        return max(self.matches, key=lambda m: m.score)

    def to_dict(self) -> dict:
        return {
            "matches": [m.to_dict() for m in self.matches],
            "search_path": self.search_path,
            "method": self.method,
            "threshold": self.threshold,
            "elapsed_ms": self.elapsed_ms,
            "template_count": self.template_count,
            "match_count": self.match_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MatchingResult:
        return cls(
            matches=[Match.from_dict(m) for m in d.get("matches", [])],
            search_path=d.get("search_path", ""),
            method=d.get("method", ""),
            threshold=d.get("threshold", 0.0),
            elapsed_ms=d.get("elapsed_ms", 0.0),
            template_count=d.get("template_count", 0),
        )
