"""Tests for field-level encryption."""

from django.test import TestCase, override_settings
from cryptography.fernet import Fernet

from core.encryption import decrypt, encrypt, mask

TEST_KEY = Fernet.generate_key().decode()


@override_settings(FIELD_ENCRYPTION_KEY=TEST_KEY)
class EncryptionTest(TestCase):
    def test_encrypt_and_decrypt_round_trip(self):
        raw = "12345678901"
        encrypted = encrypt(raw)
        self.assertTrue(encrypted.startswith("enc:"))
        self.assertNotEqual(encrypted, raw)
        self.assertEqual(decrypt(encrypted), raw)

    def test_encrypt_is_idempotent_on_encrypted_values(self):
        raw = "12345678901"
        encrypted = encrypt(raw)
        double = encrypt(encrypted)
        self.assertEqual(encrypted, double)

    def test_decrypt_plain_text_passthrough(self):
        self.assertEqual(decrypt("plain_value"), "plain_value")

    def test_decrypt_none_returns_none(self):
        self.assertIsNone(decrypt(None))

    def test_encrypt_none_returns_none(self):
        self.assertIsNone(encrypt(None))

    def test_mask_hides_most_digits(self):
        raw = "1234567890"
        encrypted = encrypt(raw)
        masked = mask(encrypted, visible=4)
        self.assertIn("7890", masked)
        self.assertNotIn("123456", masked)

    def test_different_encryptions_of_same_value_differ(self):
        """Fernet uses a random IV so two encryptions of the same value differ."""
        raw = "12345678901"
        enc1 = encrypt(raw)
        enc2 = encrypt(raw)
        self.assertNotEqual(enc1, enc2)
        self.assertEqual(decrypt(enc1), decrypt(enc2))
