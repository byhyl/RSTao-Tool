"""Abstract interface for license validation."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LicenseProvider(ABC):
    """Port for checking license/authorization status.

    Maps to: auth.py (AuthManager)
    """

    @abstractmethod
    def check_auth(self) -> tuple[bool, str]:
        """Check if the application is authorized.

        Returns: (authorized: bool, message: str)
        """
        ...

    @abstractmethod
    def check_trial(self) -> tuple[bool, str, int]:
        """Check trial status.

        Returns: (is_trial: bool, message: str, remaining_days: int)
        """
        ...
