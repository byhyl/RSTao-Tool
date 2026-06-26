"""Plugin lifecycle orchestration.  Wraps core.plugin_manager.PluginManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from core.plugin_manager import PluginInfo, PluginManager, BasePlugin

if TYPE_CHECKING:
    from .app_context import AppContext


class PluginService:
    """Orchestrates plugin lifecycle."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._manager = PluginManager()

    def discover(self) -> list[PluginInfo]:
        return self._manager.discover()

    def load_plugin(self, info: PluginInfo) -> BasePlugin | None:
        return self._manager.load_plugin(info)

    def unload_plugin(self, plugin_id: str) -> None:
        self._manager.unload_plugin(plugin_id)

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        return self._manager.get_plugin(plugin_id)

    def list_loaded(self) -> list[str]:
        return self._manager.list_loaded()

    def call_all(self, method: str, **kwargs) -> dict[str, Any]:
        return self._manager.call_all(method, **kwargs)

    def register_hook(self, hook_name: str, callback: Callable) -> None:
        self._manager.register_hook(hook_name, callback)

    def trigger_hook(self, hook_name: str, **kwargs) -> list[Any]:
        return self._manager.trigger_hook(hook_name, **kwargs)

    def set_context(self, key: str, value: Any) -> None:
        self._manager.set_context(key, value)
