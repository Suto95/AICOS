import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from aicos.api.main import app
from aicos.cosai_app import db
from aicos.cosai_app.accounts import ensure_login_email_account


class TestMigrationApi(unittest.TestCase):
    def setUp(self):
        self.original_db_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "api_test.db"
        db.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmp.cleanup()

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")

    def test_task_lifecycle(self):
        create = self.client.post(
            "/v1/users/101/tasks",
            json={"task": "Prepare migration checklist", "bucket": "DO NOW", "source": "manual"},
        )
        self.assertEqual(create.status_code, 200)
        task_id = create.json()["item"]["id"]

        listed = self.client.get("/v1/users/101/tasks")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        done = self.client.post(f"/v1/users/101/tasks/{task_id}/status", json={"status": "done"})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()["item"]["status"], "done")

        reopened = self.client.post(f"/v1/users/101/tasks/{task_id}/status", json={"status": "open"})
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["item"]["status"], "open")

    def test_insights_summary(self):
        self.client.post(
            "/v1/users/101/tasks",
            json={"task": "Task A", "bucket": "SCHEDULE", "source": "manual"},
        )
        task_id = self.client.get("/v1/users/101/tasks").json()["items"][0]["id"]
        self.client.post(f"/v1/users/101/tasks/{task_id}/status", json={"status": "done"})

        summary = self.client.get("/v1/users/101/insights/summary")
        self.assertEqual(summary.status_code, 200)
        payload = summary.json()
        self.assertEqual(payload["active_tasks"], 0)
        self.assertEqual(payload["done_tasks"], 1)

    def test_analyze_with_persist(self):
        fake_rows = [
            {
                "task": "Send status email",
                "score": 0.9,
                "bucket": "DO NOW",
                "predicted_bucket": "DO NOW",
                "reason": [],
                "meta": {"task": "Send status email"},
                "inferred": {},
                "status": "open",
                "manual_override": False,
                "override_comment": "",
                "source": "email",
                "created_at": "2026-10-20T10:00:00",
                "updated_at": "2026-10-20T10:00:00",
            }
        ]

        with patch("aicos.api.main.analyze_messages", return_value=fake_rows):
            resp = self.client.post(
                "/v1/users/101/tasks/analyze",
                json={
                    "messages": [
                        {
                            "subject": "Status",
                            "snippet": "Please send status",
                            "body": "Need this today",
                            "sender": "manager@example.com",
                            "timestamp": "2026-10-20T09:00:00+00:00",
                            "thread_id": "t1",
                            "message_id": "m1",
                        }
                    ],
                    "persist": True,
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["items"]), 1)

        listed = self.client.get("/v1/users/101/tasks")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

    def test_account_endpoints(self):
        ensure_login_email_account(101, "user@example.com")
        rows = self.client.get("/v1/users/101/accounts")
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(len(rows.json()["items"]), 1)
        account_id = rows.json()["items"][0]["id"]

        updated = self.client.patch(
            f"/v1/users/101/accounts/{account_id}/query-filter",
            json={"query_filter": "newer_than:7d"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["items"][0]["query_filter"], "newer_than:7d")

        disconnected = self.client.post(f"/v1/users/101/accounts/{account_id}/disconnect")
        self.assertEqual(disconnected.status_code, 200)
        self.assertEqual(disconnected.json()["items"], [])

    def test_me_endpoints_require_header(self):
        no_header = self.client.get("/v1/me/tasks")
        self.assertEqual(no_header.status_code, 401)

        bad_header = self.client.get("/v1/me/tasks", headers={"X-User-Id": "abc"})
        self.assertEqual(bad_header.status_code, 400)

    def test_me_endpoints_with_header(self):
        headers = {"X-User-Id": "101"}
        ensure_login_email_account(101, "user@example.com")

        create = self.client.post(
            "/v1/me/tasks",
            headers=headers,
            json={"task": "Header scoped task", "bucket": "DO NOW", "source": "manual"},
        )
        self.assertEqual(create.status_code, 200)
        task_id = create.json()["item"]["id"]

        listed = self.client.get("/v1/me/tasks", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        done = self.client.post(f"/v1/me/tasks/{task_id}/status", headers=headers, json={"status": "done"})
        self.assertEqual(done.status_code, 200)

        accounts = self.client.get("/v1/me/accounts", headers=headers)
        self.assertEqual(accounts.status_code, 200)
        self.assertEqual(len(accounts.json()["items"]), 1)

        summary = self.client.get("/v1/me/insights/summary", headers=headers)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["done_tasks"], 1)

    def test_google_oauth_start(self):
        with patch("aicos.api.main.build_google_auth_url", return_value=("https://accounts.google.com/o/oauth2/auth?x=1", "state123", "verifier123")):
            resp = self.client.post("/v1/auth/google/start", json={"redirect_uri": "http://localhost:5173/"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["auth_url"].startswith("https://accounts.google.com/"))
        self.assertEqual(payload["state"], "state123")

    def test_google_oauth_callback(self):
        with patch("aicos.api.main.pop_oauth_verifier", return_value="verifier123"), patch(
            "aicos.api.main.complete_google_oauth",
            return_value={
                "account_email": "user@example.com",
                "scopes": ["openid"],
                "access_token": "tok",
                "refresh_token": "ref",
                "token_expiry": "",
            },
        ):
            resp = self.client.post(
                "/v1/auth/google/callback",
                json={"code": "abc", "state": "state123", "redirect_uri": "http://localhost:5173/"},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["user_id"] > 0)
        self.assertEqual(payload["email"], "user@example.com")
        self.assertTrue(bool(payload.get("session_token")))

    def test_session_exchange_and_bearer_access(self):
        session = self.client.post("/v1/auth/session", json={"user_id": 101, "email": "user@example.com"})
        self.assertEqual(session.status_code, 200)
        token = session.json().get("session_token")
        self.assertTrue(bool(token))

        whoami = self.client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(whoami.status_code, 200)
        self.assertEqual(whoami.json()["user_id"], 101)
        self.assertEqual(whoami.json()["email"], "user@example.com")

        auth_headers = {"Authorization": f"Bearer {token}"}
        create = self.client.post(
            "/v1/me/tasks",
            headers=auth_headers,
            json={"task": "Bearer scoped task", "bucket": "DO NOW", "source": "manual"},
        )
        self.assertEqual(create.status_code, 200)

        listed = self.client.get("/v1/me/tasks", headers=auth_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        refreshed = self.client.post("/v1/auth/refresh", headers=auth_headers)
        self.assertEqual(refreshed.status_code, 200)
        refreshed_token = refreshed.json().get("session_token")
        self.assertTrue(bool(refreshed_token))

        refreshed_headers = {"Authorization": f"Bearer {refreshed_token}"}
        listed_again = self.client.get("/v1/me/tasks", headers=refreshed_headers)
        self.assertEqual(listed_again.status_code, 200)
        self.assertEqual(len(listed_again.json()["items"]), 1)


if __name__ == "__main__":
    unittest.main()