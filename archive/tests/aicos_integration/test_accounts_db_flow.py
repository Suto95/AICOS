import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cosai_app import db
from cosai_app.accounts import (
    cache_oauth_verifier,
    ensure_login_email_account,
    get_active_account,
    pop_oauth_verifier,
    upsert_google_account,
)


class TestAccountsDbFlow(unittest.TestCase):
    def setUp(self):
        self.original_db_path = db.DB_PATH
        self.tmpdir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmpdir.name) / "integration_accounts.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_pending_login_account_creation(self):
        account_id = ensure_login_email_account(user_id=11, email="user@example.com")
        self.assertIsInstance(account_id, int)

        with db.get_conn() as conn:
            row = conn.execute("SELECT status, account_email FROM connected_accounts WHERE id = ?", (account_id,)).fetchone()
        self.assertEqual(row["status"], "pending_auth")
        self.assertEqual(row["account_email"], "user@example.com")

    def test_oauth_upsert_and_read_active_account(self):
        ensure_login_email_account(user_id=44, email="user@example.com")
        with patch.dict(os.environ, {"COSAI_ENCRYPTION_KEY": ""}, clear=False):
            account_id = upsert_google_account(
                44,
                {
                    "account_email": "user@example.com",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly", "openid"],
                    "access_token": "access-token-1",
                    "refresh_token": "refresh-token-1",
                    "token_expiry": "2026-05-01T00:00:00",
                },
            )
        account = get_active_account(44, account_id)
        self.assertIsNotNone(account)
        self.assertEqual(account["status"], "active")
        self.assertEqual(account["access_token"], "access-token-1")
        self.assertEqual(account["refresh_token"], "refresh-token-1")

    def test_oauth_state_cache_roundtrip(self):
        cache_oauth_verifier(user_id=0, state="s1", code_verifier="v1")
        value = pop_oauth_verifier(user_id=0, state="s1")
        self.assertEqual(value, "v1")
        second = pop_oauth_verifier(user_id=0, state="s1")
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
