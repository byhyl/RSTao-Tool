"""Shared filesystem paths for runtime data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "RSTao-Tool"


def get_appdata_dir() -> Path:
    """Return the per-user writable data directory."""
    base = Path(os.getenv("APPDATA", str(Path.home())))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_dir() -> Path:
    """Return the executable/script directory used for portable installs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    argv0 = Path(sys.argv[0] or ".")
    if argv0.name in {"-c", ""}:
        return Path.cwd()
    return argv0.resolve().parent


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".rstao_write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except (OSError, PermissionError):
        return False


def resolve_user_data_path(file_name: str, prefer_runtime_dir: bool = True) -> Path:
    """Resolve a writable runtime file path with APPDATA fallback."""
    runtime_dir = get_runtime_dir()
    if prefer_runtime_dir and _is_writable_dir(runtime_dir):
        return runtime_dir / file_name
    return get_appdata_dir() / file_name


def resolve_license_path(file_name: str = ".license.dat") -> Path:
    """Resolve the canonical license file path for all app components."""
    return resolve_user_data_path(file_name)
