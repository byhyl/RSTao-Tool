"""AES-256-GCM 加密模块测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from common.crypto import aes_gcm_encrypt, aes_gcm_decrypt, generate_machine_code_hash


class TestAESGCM:
    """AES-256-GCM 加解密测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """基本加解密往返测试"""
        plain = "TEST_MACHINE|1735689600.123"
        enc = aes_gcm_encrypt(plain)
        assert enc is not None
        assert len(enc) > 0
        dec = aes_gcm_decrypt(enc)
        assert dec == plain

    def test_different_inputs_different_outputs(self):
        """不同输入产生不同密文"""
        e1 = aes_gcm_encrypt("data_a")
        e2 = aes_gcm_encrypt("data_b")
        assert e1 != e2

    def test_tamper_detection(self):
        """篡改密文应返回 None"""
        plain = "IMPORTANT_DATA"
        enc = aes_gcm_encrypt(plain)
        tampered = enc[:-4] + "XXXX"
        assert aes_gcm_decrypt(tampered) is None

    def test_cross_machine_isolation(self):
        """不同机器码密钥隔离"""
        enc_a = aes_gcm_encrypt("secret", machine_code="DEVICE_A")
        assert aes_gcm_decrypt(enc_a, machine_code="DEVICE_B") is None

    def test_empty_string(self):
        """空字符串加解密"""
        enc = aes_gcm_encrypt("")
        assert enc is not None
        assert aes_gcm_decrypt(enc) == ""

    def test_unicode_text(self):
        """Unicode 中文文本加解密"""
        plain = "用户机器码|过期时间|备注信息"
        enc = aes_gcm_encrypt(plain)
        assert aes_gcm_decrypt(enc) == plain

    def test_long_text(self):
        """长文本加解密"""
        plain = "X" * 1000
        enc = aes_gcm_encrypt(plain)
        assert aes_gcm_decrypt(enc) == plain

    def test_invalid_base64(self):
        """非法 Base64 输入"""
        assert aes_gcm_decrypt("!!!not-valid-base64!!!") is None

    def test_none_input(self):
        """None 输入"""
        assert aes_gcm_encrypt(None) is None


class TestMachineCodeHash:
    """机器码哈希测试"""

    def test_hash_length(self):
        """哈希长度验证"""
        h = generate_machine_code_hash("a1b2c3d4e5f6a7b8")
        assert len(h) == 16

    def test_hash_is_hex(self):
        """哈希为十六进制"""
        h = generate_machine_code_hash("test")
        int(h, 16)  # 不抛异常即可

    def test_deterministic(self):
        """相同输入产生相同哈希"""
        h1 = generate_machine_code_hash("SAME_INPUT")
        h2 = generate_machine_code_hash("SAME_INPUT")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        """不同输入产生不同哈希"""
        h1 = generate_machine_code_hash("INPUT_A")
        h2 = generate_machine_code_hash("INPUT_B")
        assert h1 != h2