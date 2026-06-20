"""Persistent ONNX model configuration registry."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from common.paths import get_appdata_dir, get_runtime_dir, get_settings_dir, migrate_file_once


@dataclass
class ModelConfig:
    """Configuration required for repeatable ONNX post-processing."""

    model_path: str
    name: str = ""
    class_names: list[str] = field(default_factory=list)
    input_size: tuple[int, int] = (640, 640)
    color_order: str = "BGR"
    normalization: str = "0-1"
    letterbox: bool = False
    output_format: str = "auto"
    confidence: float = 0.5
    iou_threshold: float = 0.45

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["input_size"] = list(self.input_size)
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "ModelConfig":
        data = dict(payload)
        if isinstance(data.get("input_size"), list):
            data["input_size"] = tuple(data["input_size"])
        return cls(**data)


class ModelRegistry:
    """JSON-backed registry stored under the portable settings directory."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            default_path = get_settings_dir() / "models.json"
            migrate_file_once(
                [get_appdata_dir(create=False) / "models.json", get_runtime_dir() / "models.json"],
                default_path,
            )
            self.path = default_path
        else:
            self.path = path

    def load_all(self) -> dict[str, ModelConfig]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return {
                key: ModelConfig.from_dict(value)
                for key, value in payload.items()
                if isinstance(value, dict)
            }
        except Exception:
            return {}

    def save(self, config: ModelConfig):
        configs = self.load_all()
        key = str(Path(config.model_path).resolve())
        configs[key] = config
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: v.to_dict() for k, v in configs.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, model_path: str) -> Optional[ModelConfig]:
        key = str(Path(model_path).resolve())
        return self.load_all().get(key)


def infer_model_config(
    model_path: str, confidence: float = 0.5, iou_threshold: float = 0.45
) -> ModelConfig:
    """Create a best-effort model config from an ONNX file."""
    path = Path(model_path)
    cfg = ModelConfig(
        model_path=str(path),
        name=path.stem,
        confidence=confidence,
        iou_threshold=iou_threshold,
    )
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        shape = session.get_inputs()[0].shape
        if len(shape) >= 4:
            h = shape[2] if isinstance(shape[2], int) and shape[2] > 0 else 640
            w = shape[3] if isinstance(shape[3], int) and shape[3] > 0 else 640
            cfg.input_size = (int(w), int(h))
    except Exception:
        pass
    cfg.class_names = load_adjacent_class_names(path)
    return cfg


def load_adjacent_class_names(model_path: str | Path) -> list[str]:
    """Load class names from common files next to the ONNX model."""
    path = Path(model_path)
    candidates = [
        path.with_suffix(".txt"),
        path.with_suffix(".names"),
        path.parent / "classes.txt",
        path.parent / "labels.txt",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            names = [
                line.strip()
                for line in candidate.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
            if names:
                return names
        except Exception:
            continue
    return []
