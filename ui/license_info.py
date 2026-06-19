"""License information helpers for the About dialog."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from common.license_crypto import parse_license_key
from common.logger import logger
from common.paths import resolve_license_path


class Config:
    """Global UI constants."""

    LICENSE_FILE = resolve_license_path(".license.dat")
    ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"
    RECENT_PROJECTS_MAX = 10
    UI_CONSTANTS = {
        "welcome_padx": 300,
        "ribbon_height": 60,
        "statusbar_height": 25,
        "btn_icon_size": (20, 20),
        "app_icon_size": (32, 32),
        "default_window_size": "1600x900",
        "min_window_size": (1400, 800),
    }
    PERMANENT_DATE = datetime(2099, 12, 31)


class LicenseManager:
    """Read-only license summary parser."""

    @staticmethod
    def decrypt_license(license_key: str) -> tuple[Optional[str], Optional[float]]:
        payload = parse_license_key(license_key, allow_legacy=True)
        if not payload:
            logger.error("授权解析失败: 签名无效或格式错误")
            return None, None
        try:
            return payload.get("machine_code", "").strip(), float(payload["expire_ts"])
        except Exception as e:
            logger.error(f"授权字段解析失败: {e}", exc_info=True)
            return None, None

    @staticmethod
    def get_license_info() -> Dict[str, str]:
        default_info = {
            "status": "未授权",
            "type": "无授权",
            "expire": "无",
            "remain": "无",
            "machine": "无",
        }

        license_path = resolve_license_path(".license.dat")
        Config.LICENSE_FILE = license_path
        if not license_path.exists():
            logger.info(f"授权文件不存在: {license_path}")
            return default_info

        try:
            license_key = license_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"读取授权文件失败: {e}")
            return default_info

        if not license_key:
            return {
                "status": "授权文件为空",
                "type": "无",
                "expire": "无",
                "remain": "无",
                "machine": "无",
            }

        payload = parse_license_key(license_key, allow_legacy=True)
        if not payload:
            return {
                "status": "授权无效",
                "type": "无效授权",
                "expire": "无",
                "remain": "无",
                "machine": "无",
            }

        machine = str(payload.get("machine_code", ""))
        expire_ts = float(payload.get("expire_ts", 0))
        license_type = "v2 签名授权" if payload.get("source") == "signed" else "旧版授权"
        expire_date = datetime.fromtimestamp(expire_ts)
        now = datetime.now()

        if abs((expire_date - Config.PERMANENT_DATE).days) < 10:
            return {
                "status": "已授权（永久）",
                "type": license_type,
                "machine": machine,
                "expire": "2099-12-31 永久",
                "remain": "永久有效",
            }

        remain_days_int = (expire_date - now).days
        expire_str = expire_date.strftime("%Y-%m-%d %H:%M:%S")
        if remain_days_int < 0:
            return {
                "status": f"已过期 {abs(remain_days_int)} 天",
                "type": license_type,
                "machine": machine,
                "expire": expire_str,
                "remain": f"已过期{abs(remain_days_int)}天",
            }

        return {
            "status": "正常使用",
            "type": license_type,
            "machine": machine,
            "expire": expire_str,
            "remain": f"{remain_days_int} 天",
        }
