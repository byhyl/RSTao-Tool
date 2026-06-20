"""Signed license helper tests."""

from Crypto.PublicKey import RSA

from auth import AuthManager
from common.license_crypto import (
    create_license_payload,
    sign_license_payload,
    verify_signed_license,
)


def test_signed_license_roundtrip_with_matching_public_key():
    key = RSA.generate(2048)
    payload = create_license_payload("ABCDEF1234567890", 4102444800.0, "test")

    license_key = sign_license_payload(payload, key.export_key().decode("utf-8"))
    verified = verify_signed_license(license_key, key.publickey().export_key().decode("utf-8"))

    assert verified["machine_code"] == "ABCDEF1234567890"
    assert verified["expire_ts"] == 4102444800.0
    assert verified["type"] == "test"


def test_signed_license_rejects_wrong_public_key():
    signer = RSA.generate(2048)
    other = RSA.generate(2048)
    payload = create_license_payload("ABCDEF1234567890", 4102444800.0)

    license_key = sign_license_payload(payload, signer.export_key().decode("utf-8"))

    try:
        verify_signed_license(license_key, other.publickey().export_key().decode("utf-8"))
        assert False, "expected signature verification failure"
    except Exception:
        assert True


def test_auth_rejects_unknown_machine_code(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "get_machine_code", lambda: "UNKNOWN")

    assert manager._validate_machine("UNKNOWN") == "授权机器码无效"


def test_trial_record_survives_one_missing_anchor(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "get_machine_code", lambda: "ABCDEF1234567890")
    monkeypatch.setattr(manager, "_read_trial_registry", lambda: "")
    monkeypatch.setattr(manager, "_write_trial_registry", lambda _text: None)

    assert manager.start_trial(days=1)
    manager._trial_files()[0].unlink()

    ok, message, days = manager.check_trial()

    assert ok
    assert message == "trial_active"
    assert days >= 0


def test_trial_rejects_clock_rollback(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "get_machine_code", lambda: "ABCDEF1234567890")
    monkeypatch.setattr(manager, "_read_trial_registry", lambda: "")
    monkeypatch.setattr(manager, "_write_trial_registry", lambda _text: None)

    now = 1_700_000_000.0
    record = {
        "version": 2,
        "machine_code_hash": manager.get_machine_code_hashed(),
        "trial_start": now,
        "trial_end": now + 86400,
        "last_seen": now + 7200,
        "days": 1,
    }
    record["signature"] = manager._trial_signature(record)
    monkeypatch.setattr("auth.time.time", lambda: now)
    manager._write_trial_record(record)

    ok, message, days = manager.check_trial()

    assert not ok
    assert message == "trial_clock_tamper"
    assert days == 0
