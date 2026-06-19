# common/crypto.py
"""
安全加密模块 - AES-256-GCM 加解密 + 密钥派生
版本：2.1 - 商业化安全加固（固定盐值）
"""

import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2

# ====================== 密钥派生常量 ======================
_PBKDF2_ITERATIONS = 200_000
_KEY_LENGTH = 32  # AES-256
_GCM_NONCE_LENGTH = 12
_GCM_TAG_LENGTH = 16

# 固定盐值（32 字节）—— 确保 admin 和 client 永远使用相同的密钥派生
_BUILTIN_SALT = bytes(
    [
        0xA3,
        0x7F,
        0x2C,
        0x91,
        0x4E,
        0xB8,
        0xDD,
        0x06,
        0x15,
        0x3A,
        0x6F,
        0xC4,
        0x82,
        0x1D,
        0x59,
        0xE7,
        0x30,
        0x8B,
        0x4F,
        0xA2,
        0x7E,
        0xCD,
        0x11,
        0xF5,
        0x98,
        0x26,
        0x0A,
        0x6B,
        0xD3,
        0x44,
        0x1E,
        0x9C,
    ]
)


def _derive_master_key(machine_code: str = "") -> bytes:
    """
    多层密钥派生：
    1. 内置种子 + 机器码 → 组合种子
    2. 组合种子 + 固定盐 → PBKDF2 → AES-256 密钥
    永不直接硬编码 AES 密钥
    """
    seeds = [
        b"\x47\x49\x53\x54\x6f\x6f\x6c\x32\x30\x32\x35",  # "GISTool2025"
        hashlib.sha256(b"RSTao-Commercial-v2").digest()[:16],
        bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE]),
    ]
    combined = b"".join(seeds) + machine_code.encode("utf-8")
    key = PBKDF2(
        combined,
        _BUILTIN_SALT,
        dkLen=_KEY_LENGTH,
        count=_PBKDF2_ITERATIONS,
        hmac_hash_module=SHA256,
    )
    return key


# ====================== AES-256-GCM 加解密 ======================
def aes_gcm_encrypt(plaintext: str, machine_code: str = "") -> Optional[str]:
    """
    AES-256-GCM 加密
    格式：base64(nonce[12B] + ciphertext + tag[16B])
    """
    try:
        key = _derive_master_key(machine_code)
        nonce = secrets.token_bytes(_GCM_NONCE_LENGTH)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
        payload = nonce + ciphertext + tag
        return base64.b64encode(payload).decode("utf-8")
    except Exception:
        return None


def aes_gcm_decrypt(encrypted_b64: str, machine_code: str = "") -> Optional[str]:
    """
    AES-256-GCM 解密，含完整性校验
    """
    try:
        key = _derive_master_key(machine_code)
        payload = base64.b64decode(encrypted_b64)
        if len(payload) < _GCM_NONCE_LENGTH + _GCM_TAG_LENGTH:
            return None
        nonce = payload[:_GCM_NONCE_LENGTH]
        tag = payload[-_GCM_TAG_LENGTH:]
        ciphertext = payload[_GCM_NONCE_LENGTH:-_GCM_TAG_LENGTH]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode("utf-8")
    except (ValueError, KeyError):
        return None
    except Exception:
        return None


# ====================== 辅助函数 ======================
def generate_machine_code_hash(raw_machine_code: str) -> str:
    """对机器码做哈希处理，不直接暴露原始硬件信息"""
    return hashlib.sha256(raw_machine_code.encode()).hexdigest()[:16]
