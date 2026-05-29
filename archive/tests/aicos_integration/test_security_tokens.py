import os
import unittest
from unittest.mock import patch

from cosai_app.security import decrypt_secret, encrypt_secret


class TestSecurityTokens(unittest.TestCase):
    def test_encrypt_decrypt_without_key_falls_back_to_plain_prefix(self):
        with patch.dict(os.environ, {"COSAI_ENCRYPTION_KEY": ""}, clear=False):
            encoded = encrypt_secret("my-token")
            self.assertTrue(encoded.startswith("plain::"))
            self.assertEqual(decrypt_secret(encoded), "my-token")

    def test_legacy_plaintext_is_backward_compatible(self):
        self.assertEqual(decrypt_secret("legacy-token"), "legacy-token")


if __name__ == "__main__":
    unittest.main()
