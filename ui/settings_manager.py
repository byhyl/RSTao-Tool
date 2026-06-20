"""设置持久化管理 - 读写 RSTao_Data/settings/settings.json。"""

import json
from pathlib import Path
from typing import Any, Dict

from common.paths import get_appdata_dir
from common.paths import get_cache_dir
from common.paths import get_settings_dir as get_portable_settings_dir
from common.paths import migrate_file_once


# ====================== 配置读写 ======================
def get_settings_dir() -> Path:
    """获取设置目录（自动创建）"""
    return get_portable_settings_dir()


SETTINGS_FILE = get_settings_dir() / "settings.json"
migrate_file_once([get_appdata_dir(create=False) / "settings.json"], SETTINGS_FILE)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",
    "language": "zh",
    "cache_dir": str(get_cache_dir()),
    "defaults": {
        "harris_k": 0.04,
        "susan_t": 25,
        "point_size": 4,
        "match_threshold": 0.80,
        "nms_radius": 5,
        "confidence": 0.50,
        "iou_threshold": 0.45,
    },
    "window": {
        "width": 1600,
        "height": 900,
        "x": -1,  # -1 = 居中
        "y": -1,
    },
}


def load_settings() -> Dict[str, Any]:
    """加载设置，文件不存在或损坏时返回默认值"""
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(saved)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> bool:
    """保存设置到磁盘"""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_setting(key: str, default: Any = None) -> Any:
    """读取单个设置项"""
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key: str, value: Any) -> bool:
    """写入单个设置项"""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
