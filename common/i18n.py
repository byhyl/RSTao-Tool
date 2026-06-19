"""国际化模块 - JSON 驱动的轻量级 i18n"""

import json
from pathlib import Path

_I18N_DIR = Path(__file__).parent.parent / "i18n"
_cache = {}
_current_lang = "zh"


def load_language(lang: str = "zh") -> dict:
    """加载语言包"""
    global _current_lang
    _current_lang = lang
    if lang in _cache:
        return _cache[lang]
    path = _I18N_DIR / f"{lang}.json"
    if not path.exists():
        path = _I18N_DIR / "zh.json"
    with open(path, "r", encoding="utf-8") as f:
        _cache[lang] = json.load(f)
    return _cache[lang]


def t(key: str, default: str = "") -> str:
    """翻译文本"""
    if _current_lang not in _cache:
        load_language(_current_lang)
    return _cache.get(_current_lang, {}).get(key, default or key)


def current_lang() -> str:
    return _current_lang


# 预加载中文
load_language("zh")
