"""Qt preview entry point for the migration project."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_paths() -> None:
    project_root = Path(__file__).resolve().parent
    repo_root = Path(__file__).resolve().parent.parent
    project_root_text = str(project_root)
    repo_root_text = str(repo_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


def main() -> int:
    _ensure_import_paths()
    try:
        from ui_qt.app import run
        from ui_qt.i18n import tr
    except ImportError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print(tr("console.missing_qt"))
            print('  python -m pip install -e ".[qt]"')
            return 1
        raise

    return run()


if __name__ == "__main__":
    sys.exit(main())
