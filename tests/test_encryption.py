"""Tests for encryption engine — AES-256-GCM + Argon2id."""

from __future__ import annotations

import pytest

from encryption.engine import EncryptionEngine


class TestEncryptionEngine:
    """AES-256-GCM encryption: correctness and security properties."""

    def test_encrypt_decrypt_roundtrip(self):
        engine = EncryptionEngine()
        # Override machine key for test
        engine._machine_key = b"a" * 32

        plaintext = b"The quick brown fox jumps over the lazy dog. " * 50
        encrypted = engine.encrypt_data(plaintext)
        decrypted = engine.decrypt_data(encrypted)

        assert decrypted == plaintext
        # Ciphertext should be different from plaintext
        assert encrypted.ciphertext != plaintext
        # IV should be 12 bytes
        assert len(encrypted.iv) == 12
        # Tag should be 16 bytes
        assert len(encrypted.tag) == 16

    def test_encrypt_produces_different_outputs(self):
        """Each encryption should produce unique ciphertext (unique IV)."""
        engine = EncryptionEngine()
        engine._machine_key = b"b" * 32

        plaintext = b"test data"
        e1 = engine.encrypt_data(plaintext)
        e2 = engine.encrypt_data(plaintext)

        assert e1.ciphertext != e2.ciphertext
        assert e1.iv != e2.iv

    def test_wrong_key_fails(self):
        """Decryption with wrong key must fail (GCM authentication)."""
        engine = EncryptionEngine()
        engine._machine_key = b"c" * 32

        plaintext = b"sensitive data"
        encrypted = engine.encrypt_data(plaintext)

        # Try to decrypt with different key
        wrong_key = b"d" * 32
        with pytest.raises(Exception):  # InvalidTag
            engine.decrypt_data(encrypted, key=wrong_key)

    def test_serialization_roundtrip(self):
        """Binary serialization: pack → unpack preserves all fields."""
        engine = EncryptionEngine()
        engine._machine_key = b"e" * 32

        plaintext = b"serialize me!" * 100
        encrypted = engine.encrypt_data(plaintext)
        serialized = engine._serialize(encrypted)
        deserialized = engine._deserialize(serialized)

        assert deserialized.ciphertext == encrypted.ciphertext
        assert deserialized.iv == encrypted.iv
        assert deserialized.tag == encrypted.tag
        assert deserialized.key_id == encrypted.key_id

        # Full roundtrip through serialization
        decrypted = engine.decrypt_data(deserialized)
        assert decrypted == plaintext

    def test_passphrase_encryption(self):
        """Argon2id-derived key encryption."""
        engine = EncryptionEngine()
        passphrase = "my_secure_password_2024!"

        plaintext = b"document content encrypted with passphrase"
        encrypted = engine.encrypt_with_passphrase(plaintext, passphrase)

        # Salt should be present
        assert len(encrypted.salt) == 16

        decrypted = engine.decrypt_with_passphrase(encrypted, passphrase)
        assert decrypted == plaintext

    def test_wrong_passphrase_fails(self):
        """Wrong passphrase must fail decryption."""
        engine = EncryptionEngine()
        plaintext = b"top secret"

        encrypted = engine.encrypt_with_passphrase(plaintext, "correct_password")
        with pytest.raises(Exception):
            engine.decrypt_with_passphrase(encrypted, "wrong_password")

    def test_document_encrypt_decrypt(self, tmp_path):
        """Full document encryption/decryption flow."""
        engine = EncryptionEngine()
        engine._machine_key = b"f" * 32

        doc = tmp_path / "secret.txt"
        doc.write_text("CONFIDENTIAL: Q1 financial results\nRevenue: €50M\n")

        encrypted_bytes, encrypted_data = engine.encrypt_document(doc)
        assert len(encrypted_bytes) > 0
        assert encrypted_data.key_id == "machine"

        decrypted = engine.decrypt_document(encrypted_bytes)
        assert b"Revenue" in decrypted
        assert b"CONFIDENTIAL" in decrypted


class TestEncryptionSecurityProperties:
    """Verify security properties of the encryption system."""

    def test_key_not_in_ciphertext(self):
        """The encryption key must never appear in the output."""
        engine = EncryptionEngine()
        key = b"\x01\x02\x03\x04" * 8
        engine._machine_key = key

        plaintext = b"any data"
        encrypted = engine.encrypt_data(plaintext)
        serialized = engine._serialize(encrypted)

        assert key not in serialized
        assert key not in encrypted.ciphertext
        assert key not in encrypted.iv

    def test_empty_plaintext_encrypts(self):
        """Empty documents should encrypt without error."""
        engine = EncryptionEngine()
        engine._machine_key = b"g" * 32

        encrypted = engine.encrypt_data(b"")
        decrypted = engine.decrypt_data(encrypted)
        assert decrypted == b""
