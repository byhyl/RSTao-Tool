"""Application service layer for RSTao-Tool migration.

Services coordinate between the UI (ui_qt/) and the core/data/common modules.
Services never import from ui_qt/ to avoid reverse dependencies.
"""

from __future__ import annotations

from .app_context import AppContext

__all__ = ["AppContext"]
