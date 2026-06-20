"""Portable catalog of recently imported resources."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from common.paths import get_resources_data_dir

CATALOG_LIMIT = 500


def get_resource_catalog_path() -> Path:
    return get_resources_data_dir() / "resources.json"


def load_resource_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    catalog_path = path or get_resource_catalog_path()
    if not catalog_path.exists():
        return []
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def save_resource_catalog(resources: list[dict[str, Any]], path: Path | None = None) -> None:
    catalog_path = path or get_resource_catalog_path()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(resources[:CATALOG_LIMIT], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_resource(resource: dict[str, Any], path: Path | None = None) -> None:
    """Record a resource in the portable catalog without affecting project state."""
    if not resource:
        return
    catalog = load_resource_catalog(path)
    key = resource.get("resource_id") or resource.get("source_path") or resource.get("path")
    if key:
        catalog = [
            item
            for item in catalog
            if (item.get("resource_id") or item.get("source_path") or item.get("path")) != key
        ]
    entry = dict(resource)
    entry["catalog_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    catalog.insert(0, entry)
    save_resource_catalog(catalog, path)
