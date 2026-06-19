"""插件管理器 — 可扩展的插件系统"""

import importlib
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from common.logger import logger

# ====================== 插件接口定义 ======================


@dataclass
class PluginInfo:
    """插件元信息"""

    id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    category: str = "general"  # detection / matching / export / tool
    enabled: bool = True
    entry_point: str = ""  # module:class
    dependencies: List[str] = field(default_factory=list)


class BasePlugin(ABC):
    """插件基类 — 所有插件必须继承此类"""

    def __init__(self):
        self._info: Optional[PluginInfo] = None

    @abstractmethod
    def info(self) -> PluginInfo:
        """返回插件元信息"""
        ...

    @abstractmethod
    def on_load(self, context: Dict[str, Any]) -> bool:
        """插件加载时调用，返回 True 表示加载成功"""
        ...

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def execute(self, **kwargs) -> Any:
        """执行插件核心功能"""
        raise NotImplementedError

    def get_ui_panel(self, parent) -> Any:
        """返回 UI 面板（可选），返回 None 表示无界面"""
        return None


# ====================== 插件管理器 ======================


class PluginManager:
    """插件管理器 — 发现、加载、卸载插件"""

    def __init__(self, plugins_dir: str = ""):
        self.plugins_dir = (
            Path(plugins_dir) if plugins_dir else Path(__file__).parent.parent / "plugins"
        )
        self._plugins: Dict[str, BasePlugin] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        self._context: Dict[str, Any] = {}

    def set_context(self, key: str, value: Any):
        """设置全局上下文"""
        self._context[key] = value

    def discover(self) -> List[PluginInfo]:
        """扫描插件目录，返回发现的插件列表"""
        discovered = []
        plugins_dir = self.plugins_dir
        if not plugins_dir.exists():
            plugins_dir.mkdir(parents=True, exist_ok=True)
            self._create_init(plugins_dir)
            return discovered

        for item in plugins_dir.iterdir():
            if item.is_dir() and (item / "plugin.json").exists():
                try:
                    info = json.loads((item / "plugin.json").read_text(encoding="utf-8"))
                    discovered.append(PluginInfo(**info))
                except Exception as e:
                    logger.warning(f"解析插件 {item.name} 失败: {e}")
        return discovered

    def load_plugin(self, info: PluginInfo) -> Optional[BasePlugin]:
        """加载单个插件"""
        if info.id in self._plugins:
            logger.warning(f"插件 {info.id} 已加载")
            return self._plugins[info.id]

        try:
            # 将插件目录加入 sys.path
            plugin_path = str(self.plugins_dir / info.id)
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)

            module_name, class_name = info.entry_point.split(":")
            module = importlib.import_module(module_name)
            plugin_cls: Type[BasePlugin] = getattr(module, class_name)
            plugin = plugin_cls()

            if plugin.on_load(self._context):
                self._plugins[info.id] = plugin
                logger.info(f"插件加载成功: {info.name} v{info.version}")
                return plugin
            else:
                logger.warning(f"插件 {info.id} 加载被拒绝")
        except Exception as e:
            logger.error(f"加载插件 {info.id} 失败: {e}")
        return None

    def unload_plugin(self, plugin_id: str):
        """卸载插件"""
        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            plugin.on_unload()
            logger.info(f"插件已卸载: {plugin_id}")

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        return self._plugins.get(plugin_id)

    def list_loaded(self) -> List[str]:
        return list(self._plugins.keys())

    def call_all(self, method: str, **kwargs) -> Dict[str, Any]:
        """调用所有已加载插件的指定方法"""
        results = {}
        for pid, plugin in self._plugins.items():
            try:
                func = getattr(plugin, method, None)
                if func:
                    results[pid] = func(**kwargs)
            except Exception as e:
                logger.error(f"插件 {pid}.{method}() 异常: {e}")
                results[pid] = None
        return results

    # ---- 钩子系统 ----
    def register_hook(self, hook_name: str, callback: Callable):
        """注册钩子"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def trigger_hook(self, hook_name: str, **kwargs) -> List[Any]:
        """触发钩子"""
        results = []
        for cb in self._hooks.get(hook_name, []):
            try:
                results.append(cb(**kwargs))
            except Exception as e:
                logger.error(f"钩子 {hook_name} 异常: {e}")
        return results

    @staticmethod
    def _create_init(plugins_dir: Path):
        """创建插件目录 __init__.py"""
        init_file = plugins_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text(
                "# RSTao-Tool 插件目录\n"
                "# 在此目录下创建子文件夹，每个文件夹包含 plugin.json\n"
                "# 示例结构：\n"
                "#   plugins/my_plugin/\n"
                "#     plugin.json\n"
                "#     __init__.py\n"
                "#     my_plugin.py\n",
                encoding="utf-8",
            )


# ====================== 示例插件（模板） ======================


class ExamplePlugin(BasePlugin):
    """示例插件 — 供开发者参考"""

    def info(self) -> PluginInfo:
        return PluginInfo(
            id="example",
            name="示例插件",
            version="1.0.0",
            author="RSTao",
            description="一个示例插件，展示插件开发模式",
            category="tool",
            entry_point="example_plugin:ExamplePlugin",
        )

    def on_load(self, context) -> bool:
        logger.info("示例插件已加载")
        return True

    def on_unload(self):
        logger.info("示例插件已卸载")

    def execute(self, **kwargs) -> Any:
        return {"status": "ok", "message": "示例插件执行成功"}
