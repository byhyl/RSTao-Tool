"""Signed license helper tests."""

from Crypto.PublicKey import RSA

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
