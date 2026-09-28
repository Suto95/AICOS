import unittest

from cosai_app.ui import merge_new_results


class TestImportMerge(unittest.TestCase):
    def test_merge_new_results_skips_existing_thread_duplicates(self):
        existing = [
            {
                "id": 4,
                "task": "Review vendor contract",
                "meta": {"thread_id": "thread-1"},
                "status": "open",
                "manual_override": True,
            }
        ]
        incoming = [
            {
                "id": 0,
                "task": "Review vendor contract",
                "meta": {"thread_id": "thread-1"},
                "status": "open",
                "manual_override": False,
            },
            {
                "id": 1,
                "task": "Send invoice to finance",
                "meta": {"thread_id": "thread-2"},
                "status": "open",
                "manual_override": False,
            },
        ]

        merged, added_count, added_results = merge_new_results(existing, incoming)

        self.assertEqual(added_count, 1)
        self.assertEqual(len(added_results), 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["id"], 4)
        self.assertTrue(merged[0]["manual_override"])
        self.assertEqual(merged[1]["id"], 5)
        self.assertEqual(merged[1]["task"], "Send invoice to finance")


if __name__ == "__main__":
    unittest.main()
