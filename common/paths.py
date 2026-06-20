"""Shared filesystem paths for portable runtime data."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

APP_DIR_NAME = "RSTao-Tool"
DATA_DIR_NAME = "RSTao_Data"


def get_appdata_dir(create: bool = True) -> Path:
    """Return the per-user fallback data directory."""
    base = Path(os.getenv("APPDATA", str(Path.home())))
    path = base / APP_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_dir() -> Path:
    """Return the executable/script directory used for portable installs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".rstao_write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except (OSError, PermissionError):
        return False


def get_portable_data_dir(prefer_runtime_dir: bool = True) -> Path:
    """Return the unified application data directory.

    Portable deployments write to ``<software_dir>/RSTao_Data``. If that
    directory is not writable, the app falls back to a per-user location so the
    application still starts on locked-down client machines.
    """
    override = os.getenv("RSTAO_DATA_DIR") or os.getenv("RSTAO_PORTABLE_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    runtime_data = get_runtime_dir() / DATA_DIR_NAME
    if prefer_runtime_dir and _is_writable_dir(runtime_data):
        return runtime_data

    fallback = get_appdata_dir() / DATA_DIR_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _data_subdir(name: str | Path, prefer_runtime_dir: bool = True) -> Path:
    path = get_portable_data_dir(prefer_runtime_dir=prefer_runtime_dir) / Path(name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_license_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("license", prefer_runtime_dir=prefer_runtime_dir)


def get_settings_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("settings", prefer_runtime_dir=prefer_runtime_dir)


def get_logs_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("logs", prefer_runtime_dir=prefer_runtime_dir)


def get_temp_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("temp", prefer_runtime_dir=prefer_runtime_dir)


def get_cache_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("cache", prefer_runtime_dir=prefer_runtime_dir)


def get_admin_data_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("admin", prefer_runtime_dir=prefer_runtime_dir)


def get_server_data_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("server", prefer_runtime_dir=prefer_runtime_dir)


def get_resources_data_dir(prefer_runtime_dir: bool = True) -> Path:
    return _data_subdir("resources", prefer_runtime_dir=prefer_runtime_dir)


def resolve_user_data_path(
    file_name: str,
    prefer_runtime_dir: bool = True,
    subdir: str | Path | None = None,
) -> Path:
    """Resolve a writable file path under the unified data directory."""
    base = get_portable_data_dir(prefer_runtime_dir=prefer_runtime_dir)
    if subdir:
        base = base / Path(subdir)
        base.mkdir(parents=True, exist_ok=True)
    return base / file_name


def resolve_license_path(file_name: str = ".license.dat") -> Path:
    """Resolve the canonical license file path for all app components."""
    return resolve_user_data_path(file_name, subdir="license")


def migrate_file_once(old_paths: Iterable[str | Path], new_path: str | Path) -> Path | None:
    """Copy the first existing legacy file to ``new_path`` if needed.

    The source file is intentionally preserved. This keeps upgrades safe while
    moving future reads/writes into the portable data folder.
    """
    target = Path(new_path)
    if target.exists():
        return None

    for old_path in old_paths:
        source = Path(old_path)
        try:
            if source.resolve() == target.resolve():
                continue
        except Exception:
            pass
        if not source.exists() or not source.is_file():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return source
        except Exception:
            continue
    return None
