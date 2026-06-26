"""License validation and status queries.

Note: temporarily imports from ui.license_info and auth.
These modules should eventually move to common/ or core/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.logger import logger

if TYPE_CHECKING:
    from .app_context import AppContext


class LicenseService:
    """License validation and status query service."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    def get_license_info(self) -> dict[str, str]:
        """Get a human-readable license status summary."""
        try:
            from ui.license_info import LicenseManager
            return LicenseManager.get_license_info()
        except Exception as exc:
            logger.debug("获取许可证信息失败: %s", exc)
            return {"状态": "未知"}

    def check_auth(self) -> tuple[bool, str]:
        """Check if the app is authorized. Returns (authorized, message)."""
        try:
            from auth import AuthManager
            mgr = AuthManager()
            return mgr.check()
        except Exception as exc:
            logger.debug("认证检查失败: %s", exc)
            return True, ""

    def is_admin(self) -> bool:
        """True if running as admin tool."""
        try:
            from auth import AuthManager
            mgr = AuthManager()
            return mgr.is_admin()
        except Exception:
            return False
