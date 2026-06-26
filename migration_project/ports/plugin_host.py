"""Abstract interface for plugin lifecycle management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# PluginInfo is already a pure dataclass in core/ with no UI/data dependencies.
# It is safe as a shared type — duplicating it adds no value.
from core.plugin_manager import PluginInfo


class PluginHost(ABC):
    """Port for discovering, loading, and managing plugins.

    Maps to: core/plugin_manager.py (PluginManager)
    """

    @abstractmethod
    def discover(self) -> list[PluginInfo]:
        """Scan plugin directories and return discovered plugins."""
        ...

    @abstractmethod
    def load(self, info: PluginInfo) -> Any:
        """Load a plugin. Returns the plugin instance or None."""
        ...

    @abstractmethod
    def unload(self, plugin_id: str) -> None:
        """Unload a plugin by its id."""
        ...

    @abstractmethod
    def trigger_hook(self, name: str, **kwargs: Any) -> list[Any]:
        """Trigger a named hook across all loaded plugins.

        Returns a list of callback return values.
        """
        ...
