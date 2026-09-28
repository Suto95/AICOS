import tempfile
import unittest
from pathlib import Path

from cosai_app import db
from cosai_app.data import append_event, load_events_all_users, load_persisted_tasks


class TestDataEvents(unittest.TestCase):
    def test_load_events_all_users(self):
        original_db_path = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "qa_test.db"
            db.init_db()

            append_event("task_created_manual", 1, "alpha task", {"source": "manual"}, user_id=101)
            append_event("task_deleted", 2, "newsletter promo", {"source": "email"}, user_id=202)

            rows = load_events_all_users(limit=20)
            self.assertEqual(len(rows), 2)
            user_ids = {r.get("_user_id") for r in rows}
            self.assertEqual(user_ids, {101, 202})

            rows_excluding_101 = load_events_all_users(limit=20, exclude_user_id=101)
            self.assertEqual(len(rows_excluding_101), 1)
            self.assertEqual(rows_excluding_101[0].get("_user_id"), 202)

        db.DB_PATH = original_db_path

    def test_load_persisted_tasks_replays_snapshots_and_mutations(self):
        original_db_path = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "qa_tasks.db"
            db.init_db()

            task = {
                "id": 7,
                "task": "Submit invoice",
                "score": 0.6,
                "bucket": "DO NOW",
                "predicted_bucket": "DO NOW",
                "reason": [],
                "meta": {"task": "Submit invoice"},
                "inferred": {},
                "status": "open",
                "manual_override": True,
                "override_comment": "",
                "source": "manual",
                "created_at": "2026-09-27T10:00:00",
                "updated_at": "2026-09-27T10:00:00",
            }
            append_event("task_created_manual", 7, "Submit invoice", {"task_snapshot": task}, user_id=101)

            updated = {**task, "bucket": "SCHEDULE", "updated_at": "2026-09-27T10:05:00"}
            append_event(
                "bucket_changed",
                7,
                "Submit invoice",
                {"to_bucket": "SCHEDULE", "task_snapshot": updated},
                user_id=101,
            )

            tasks = load_persisted_tasks(user_id=101)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["id"], 7)
            self.assertEqual(tasks[0]["task"], "Submit invoice")
            self.assertEqual(tasks[0]["bucket"], "SCHEDULE")
            self.assertEqual(tasks[0]["status"], "open")

        db.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
