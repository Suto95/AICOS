import tempfile
import unittest
from pathlib import Path

from cosai_app import db
from cosai_app.data import append_event, load_events_all_users


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


if __name__ == "__main__":
    unittest.main()
