"""Authorization manager used by the main app and activation UI."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import wmi

from common.crypto import aes_gcm_decrypt, aes_gcm_encrypt, generate_machine_code_hash
from common.license_crypto import parse_license_key
from common.logger import logger
from common.paths import get_appdata_dir, resolve_license_path

_TRIAL_VERSION = 2
_TRIAL_SECRET = b"RSTao-Tool-trial-record-v2"


@dataclass
class AuthConfig:
    LICENSE_FILE_NAME: str = ".license.dat"
    ACTIVATION_WINDOW_SIZE: str = "500x420"
    ACTIVATION_WINDOW_TITLE: str = "RSTao-Tool - 软件激活"
    FONT_MAIN: tuple = ("Microsoft YaHei", 14)
    FONT_SMALL: tuple = ("Microsoft YaHei", 12)
    BTN_ACTIVE_COLOR: str = "#2563eb"
    ACTIVATION_SERVER_URL: str = "http://127.0.0.1:18080"
    ACTIVATION_TIMEOUT: int = 30
    ALLOW_LEGACY_LICENSE: bool = os.getenv("RSTAO_ALLOW_LEGACY_LICENSE", "0") == "1"


class AuthManager:
    """Read, validate, activate, and persist software authorization."""

    def __init__(self, config: AuthConfig = AuthConfig()):
        self.config = config
        self.license_path = resolve_license_path(self.config.LICENSE_FILE_NAME)
        self._anti_tamper_file = self.license_path.parent / ".rstao_ts"
        self._machine_code: Optional[str] = None

    def encrypt_data(self, text: str) -> Optional[str]:
        """Legacy helper retained for compatibility tests and migration tools."""
        return aes_gcm_encrypt(text)

    def decrypt_data(self, text: str) -> Optional[str]:
        """Legacy helper retained for compatibility tests and migration tools."""
        return aes_gcm_decrypt(text)

    def get_machine_code(self) -> str:
        """Return the current device machine code."""
        if self._machine_code:
            return self._machine_code
        try:
            c = wmi.WMI()
            cpu_info = c.Win32_Processor()[0]
            cpu_id = cpu_info.ProcessorId.strip() if hasattr(cpu_info, "ProcessorId") else ""

            try:
                disk_info = c.Win32_PhysicalMedia()[0]
                disk_sn = (
                    disk_info.SerialNumber.strip() if hasattr(disk_info, "SerialNumber") else ""
                )
            except Exception:
                disk_sn = ""

            machine_str = f"{cpu_id}_{disk_sn}"
            if not machine_str.strip("_"):
                raise ValueError("无法获取有效硬件信息")

            self._machine_code = hashlib.md5(machine_str.encode("utf-8")).hexdigest()[:16]
            return self._machine_code
        except ImportError:
            logger.error("缺少 wmi 依赖，无法获取机器码")
        except IndexError:
            logger.error("未读取到 CPU 或磁盘硬件信息")
        except Exception as e:
            logger.error(f"获取机器码失败: {e}", exc_info=True)

        self._machine_code = "UNKNOWN"
        return "UNKNOWN"

    def get_machine_code_hashed(self) -> str:
        return generate_machine_code_hash(self.get_machine_code())

    def get_device_fingerprint(self) -> str:
        try:
            return str(uuid.getnode()) + "_" + self.get_machine_code()
        except Exception:
            return "UNKNOWN_" + str(uuid.getnode())

    def read_auth(self) -> Optional[str]:
        if not self.license_path.exists():
            logger.info("授权文件不存在")
            return None
        try:
            content = self.license_path.read_text(encoding="utf-8").strip()
            if not content:
                logger.warning("授权文件为空")
                return None
            return content
        except Exception as e:
            logger.error(f"读取授权文件失败: {e}", exc_info=True)
            return None

    def write_auth(self, data: str) -> bool:
        for attempt in range(3):
            try:
                self.license_path.parent.mkdir(parents=True, exist_ok=True)
                self.license_path.write_text(data, encoding="utf-8")
                self._hide_file(self.license_path)
                return True
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                logger.error(f"没有权限写入授权文件: {self.license_path}", exc_info=True)
                return False
            except Exception as e:
                logger.error(f"写入授权文件失败: {e}", exc_info=True)
                return False
        return False

    def check_auth(self) -> Tuple[bool, str]:
        license_key = self.read_auth()
        if not license_key:
            return False, "未找到授权文件"

        payload = self._parse_license(license_key)
        if not payload:
            return False, "授权无效或签名校验失败"

        machine_msg = self._validate_machine(payload.get("machine_code", ""))
        if machine_msg:
            return False, machine_msg

        tamper_msg = self._check_clock_tamper()
        if tamper_msg:
            return False, tamper_msg

        try:
            expire_ts = float(payload["expire_ts"])
            expire_date = datetime.fromtimestamp(expire_ts)
            if datetime.now() > expire_date:
                return False, f"授权已过期 ({expire_date.strftime('%Y-%m-%d')})"
        except (ValueError, KeyError, OSError):
            return False, "授权有效期格式错误"

        self._save_last_valid_time()
        return True, "授权有效"

    def is_expired(self, expire_str: str) -> bool:
        try:
            return datetime.now() > datetime.fromtimestamp(float(expire_str))
        except Exception:
            return True

    def save_license(self, key: str) -> bool:
        """Validate and persist a license key."""
        if not key or len(key.strip()) < 10:
            return False
        key = key.strip()
        payload = self._parse_license(key)
        if not payload:
            logger.warning("授权解析失败，未写入")
            return False

        machine_msg = self._validate_machine(payload.get("machine_code", ""))
        if machine_msg:
            logger.warning(machine_msg)
            return False

        try:
            expire_ts = float(payload["expire_ts"])
            if datetime.now() > datetime.fromtimestamp(expire_ts):
                logger.warning("授权已过期，未写入")
                return False
        except Exception:
            logger.warning("授权有效期无效，未写入")
            return False

        self._clean_invalid_license()
        if self.write_auth(key):
            self._reset_anti_tamper()
            return True
        return False

    def online_activate(self, activation_code: str, server_url: str = None) -> Tuple[bool, str]:
        """Activate with a remote activation server."""
        if server_url is None:
            server_url = self.config.ACTIVATION_SERVER_URL
        url = f"{server_url.rstrip('/')}/api/activate"
        payload = json.dumps(
            {
                "activation_code": activation_code.strip().upper(),
                "device_fingerprint": self.get_device_fingerprint(),
                "machine_code_hash": self.get_machine_code_hashed(),
                "machine_code": self.get_machine_code(),
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(
                req, timeout=max(self.config.ACTIVATION_TIMEOUT, 30)
            ) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            logger.error(f"激活服务器返回错误: {e.code} - {error_body}")
            return False, f"激活服务器错误 ({e.code})"
        except urllib.error.URLError as e:
            logger.error(f"无法连接激活服务器: {e.reason}")
            return False, f"无法连接激活服务器: {server_url}\n请检查网络或服务器地址。"
        except Exception as e:
            logger.error(f"在线激活异常: {e}", exc_info=True)
            return False, f"激活异常: {e}"

        if result.get("success"):
            license_key = result.get("license_key", "")
            if license_key and self.save_license(license_key):
                return True, "激活成功"
            logger.error("激活失败: save_license 返回 False")
            return False, "激活成功但授权保存失败，请检查写入权限。"
        return False, result.get("message", "激活失败")

    # ====================== Trial Mode ======================
    def check_trial(self) -> Tuple[bool, str, int]:
        """Return (valid, message, days_remaining)."""
        existing_files = [p for p in self._trial_files() if p.exists()]
        if not existing_files:
            return True, "trial_available", 7

        valid_records = []
        invalid_found = False
        for path in existing_files:
            record = self._read_trial_record(path)
            if record:
                valid_records.append(record)
            else:
                invalid_found = True

        if not valid_records:
            return False, "trial_invalid", 0

        record = min(valid_records, key=lambda item: float(item.get("trial_end", 0)))
        trial_end = float(record["trial_end"])
        remaining = max(0, int((trial_end - time.time()) / 86400))
        if time.time() < trial_end:
            self._write_trial_record(record)
            return True, "trial_active", remaining
        if invalid_found:
            logger.warning("试用记录存在损坏文件")
        return False, "trial_expired", 0

    def start_trial(self, days: int = 7) -> bool:
        """Start a signed trial period."""
        try:
            now = time.time()
            record = {
                "version": _TRIAL_VERSION,
                "machine_code_hash": self.get_machine_code_hashed(),
                "trial_start": now,
                "trial_end": now + days * 86400,
                "days": int(days),
            }
            record["signature"] = self._trial_signature(record)
            self._write_trial_record(record)
            return True
        except Exception as e:
            logger.error(f"启动试用失败: {e}", exc_info=True)
            return False

    def has_trial_available(self) -> bool:
        return not any(path.exists() for path in self._trial_files())

    # ====================== Internal helpers ======================
    def _parse_license(self, license_key: str) -> Optional[dict]:
        payload = parse_license_key(license_key, allow_legacy=self.config.ALLOW_LEGACY_LICENSE)
        if payload and payload.get("source") == "legacy":
            logger.warning("正在使用旧版 AES 授权兼容模式，请尽快迁移到 v2 签名授权")
        return payload

    def _validate_machine(self, machine_code_in_license: str) -> str:
        current_machine = self.get_machine_code()
        expected = (machine_code_in_license or "").strip()
        if not expected:
            return "授权缺少机器码"
        if current_machine == "UNKNOWN":
            if expected == "UNKNOWN":
                return ""
            return "无法获取本机机器码，不能验证授权绑定"
        if expected != current_machine:
            logger.warning(
                f"机器码不匹配: license={expected[:8]}... local={current_machine[:8]}..."
            )
            return "机器码不匹配"
        return ""

    def _trial_files(self) -> list[Path]:
        appdata_path = get_appdata_dir() / ".rstao_trial"
        runtime_path = self.license_path.parent / ".rstao_trial"
        if appdata_path == runtime_path:
            return [runtime_path]
        return [runtime_path, appdata_path]

    def _trial_signature(self, record: dict) -> str:
        payload = {
            "version": record.get("version"),
            "machine_code_hash": record.get("machine_code_hash"),
            "trial_start": float(record.get("trial_start", 0)),
            "trial_end": float(record.get("trial_end", 0)),
            "days": int(record.get("days", 0)),
        }
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = _TRIAL_SECRET + self.get_machine_code_hashed().encode("utf-8")
        return hmac.new(key, data, hashlib.sha256).hexdigest()

    def _read_trial_record(self, path: Path) -> Optional[dict]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("version") != _TRIAL_VERSION:
                return None
            if record.get("machine_code_hash") != self.get_machine_code_hashed():
                return None
            signature = record.get("signature", "")
            if not hmac.compare_digest(signature, self._trial_signature(record)):
                return None
            return record
        except Exception:
            return None

    def _write_trial_record(self, record: dict):
        text = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
        for path in self._trial_files():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                self._hide_file(path)
            except Exception as e:
                logger.warning(f"写入试用记录失败: {path} ({e})")

    def _reset_anti_tamper(self):
        try:
            if self._anti_tamper_file.exists():
                self._anti_tamper_file.unlink()
        except Exception:
            pass

    def _check_clock_tamper(self) -> str:
        if not self._anti_tamper_file.exists():
            return ""
        try:
            last_timestamp = float(self._anti_tamper_file.read_text(encoding="utf-8").strip())
            if time.time() < last_timestamp - 3600:
                return "检测到系统时间异常，请校准时间后重试"
        except Exception:
            pass
        return ""

    def _save_last_valid_time(self):
        try:
            self._anti_tamper_file.write_text(str(time.time()), encoding="utf-8")
            self._hide_file(self._anti_tamper_file)
        except Exception:
            pass

    def _clean_invalid_license(self):
        try:
            if self.license_path.exists():
                self.license_path.unlink()
                logger.info("已删除旧授权文件")
        except Exception as e:
            logger.error(f"删除旧授权失败: {e}")

    @staticmethod
    def _hide_file(path: Path):
        if sys.platform != "win32":
            return
        try:
            subprocess.run(
                ["attrib", "+h", str(path)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
