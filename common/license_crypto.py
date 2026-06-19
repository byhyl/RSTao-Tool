"""Signed license helpers.

The client verifies licenses with a bundled public key. The private key must stay
outside the client package and is only loaded by the admin tool from an
environment variable or a local PEM file.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

from common.crypto import aes_gcm_decrypt

LICENSE_KEY_PREFIX = "RSTAO-LIC-v2."

BUNDLED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAznS9wywhppCaCoWCmHKO
pxDPHgboQ3ugQy5ekigfW6E+0P52XOgYeUTaQHEPKS9YdHT8s+/s3P4eYv+FsPrD
aKAgshLp7zsGSgoRPpyB/HQ97nvq76uPDOZ9/tOnXsbKTSh7w3ZtLScxntGng0X2
dC3zIhkMduc53tBctIQP5LCq8Gq+mR/9NhI7XTL/sDQuS8Z4+LmP5r2jMQzQCxgW
nt6HIzL0Ydlk1PbSDj4vcbDpcyz8N20EOb0fACBOzjXQS4qpKoz8+Wn94vmjnWff
tM1KDJ+SKZGSXRZLX+j9lo+eSQa+G0itYVHyY0OSh9OUJ12sivbrbVeXSVGyD1HL
8QIDAQAB
-----END PUBLIC KEY-----"""


class LicenseCryptoError(ValueError):
    """Raised when a signed license cannot be parsed or verified."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def canonical_payload_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def create_license_payload(
    machine_code: str,
    expire_ts: float,
    license_type: str = "standard",
    features: Optional[list[str]] = None,
) -> Dict[str, Any]:
    return {
        "version": 2,
        "issued_at": int(time.time()),
        "machine_code": machine_code.strip(),
        "expire_ts": float(expire_ts),
        "type": license_type,
        "features": features or [],
    }


def sign_license_payload(payload: Dict[str, Any], private_key_pem: str) -> str:
    key = RSA.import_key(private_key_pem)
    if not key.has_private():
        raise LicenseCryptoError("授权私钥无效")
    body = canonical_payload_bytes(payload)
    signature = pkcs1_15.new(key).sign(SHA256.new(body))
    return LICENSE_KEY_PREFIX + _b64url_encode(body) + "." + _b64url_encode(signature)


def verify_signed_license(
    license_key: str, public_key_pem: str = BUNDLED_PUBLIC_KEY
) -> Dict[str, Any]:
    if not license_key.startswith(LICENSE_KEY_PREFIX):
        raise LicenseCryptoError("不是 v2 签名授权")
    parts = license_key[len(LICENSE_KEY_PREFIX) :].split(".")
    if len(parts) != 2:
        raise LicenseCryptoError("授权格式错误")
    body = _b64url_decode(parts[0])
    signature = _b64url_decode(parts[1])
    key = RSA.import_key(public_key_pem)
    pkcs1_15.new(key).verify(SHA256.new(body), signature)
    payload = json.loads(body.decode("utf-8"))
    if payload.get("version") != 2:
        raise LicenseCryptoError("授权版本不支持")
    if "machine_code" not in payload or "expire_ts" not in payload:
        raise LicenseCryptoError("授权字段不完整")
    return payload


def parse_license_key(license_key: str, allow_legacy: bool = False) -> Optional[Dict[str, Any]]:
    try:
        payload = verify_signed_license(license_key)
        payload["source"] = "signed"
        return payload
    except Exception:
        if not allow_legacy:
            return None

    decrypted = aes_gcm_decrypt(license_key)
    if not decrypted:
        return None
    parts = decrypted.split("|")
    if len(parts) < 2:
        return None
    try:
        return {
            "version": 1,
            "machine_code": parts[0].strip(),
            "expire_ts": float(parts[-1].strip()),
            "type": "legacy",
            "features": [],
            "source": "legacy",
        }
    except ValueError:
        return None


def load_private_key_from_env() -> Optional[str]:
    """Load admin signing private key from env var or env-pointed PEM file."""
    explicit_file = os.getenv("RSTAO_LICENSE_PRIVATE_KEY_FILE")
    if explicit_file:
        path = Path(explicit_file)
        if path.exists():
            return path.read_text(encoding="utf-8")

    value = os.getenv("RSTAO_LICENSE_PRIVATE_KEY")
    if value:
        path = Path(value)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return value.replace("\\n", "\n")

    root = Path(__file__).resolve().parent.parent
    for candidate in (Path.cwd() / "admin_license_private.pem", root / "admin_license_private.pem"):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def private_key_matches_public(
    private_key_pem: str, public_key_pem: str = BUNDLED_PUBLIC_KEY
) -> bool:
    try:
        private_key = RSA.import_key(private_key_pem)
        public_key = RSA.import_key(public_key_pem)
        return (
            private_key.publickey().n == public_key.n and private_key.publickey().e == public_key.e
        )
    except Exception:
        return False
