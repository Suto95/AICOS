import unittest
from unittest.mock import patch

from cosai_app.logic import (
    analyze_messages,
    derive_user_hint_profile,
    merge_hint_profiles,
)


class TestE2EMessagePipeline(unittest.TestCase):
    def test_cross_user_hints_affect_task_like_filtering_and_pipeline(self):
        user_events = [
            {"event_type": "task_created_manual", "task_text": "submit invoice to finance", "payload": {"account_id": 9}},
            {"event_type": "task_created_manual", "task_text": "finance invoice submission", "payload": {"account_id": 9}},
        ]
        global_events = [
            {"event_type": "task_deleted", "task_text": "weekly newsletter discount promo", "payload": {"source": "email", "sender_domain": "ads.example.com"}},
            {"event_type": "task_deleted", "task_text": "newsletter promo offer discount", "payload": {"source": "email", "sender_domain": "ads.example.com"}},
            {"event_type": "task_deleted", "task_text": "newsletter promo offer discount", "payload": {"source": "email", "sender_domain": "ads.example.com"}},
            {"event_type": "task_deleted", "task_text": "newsletter promo offer discount", "payload": {"source": "email", "sender_domain": "ads.example.com"}},
            {"event_type": "task_deleted", "task_text": "newsletter promo offer discount", "payload": {"source": "email", "sender_domain": "ads.example.com"}},
        ]
        user_profile = derive_user_hint_profile(user_events, account_id=9)
        global_profile = derive_user_hint_profile(
            global_events,
            min_action_count=5,
            min_noise_count=2,
            min_noise_domain_count=3,
        )
        hint_profile = merge_hint_profiles(user_profile, global_profile)

        messages = [
            {
                "text": "Invoice submission needed",
                "subject": "Invoice submission needed",
                "snippet": "Please submit invoice by tomorrow",
                "body": "Need action from finance team",
                "sender": "ops@example.com",
                "timestamp": "2026-04-24T10:00:00+05:30",
                "thread_id": "t1",
                "message_id": "m1",
            },
            {
                "text": "Newsletter promo",
                "subject": "Weekly newsletter discount promo",
                "snippet": "Offer just for you",
                "body": "unsubscribe",
                "sender": "ads@ads.example.com",
                "timestamp": "2026-04-24T10:10:00+05:30",
                "thread_id": "t2",
                "message_id": "m2",
            },
        ]

        mock_extracted = {
            "task": "Submit invoice to finance",
            "deadline": "2026-04-25",
            "urgency_signal": "high",
            "importance_signal": "high",
            "penalty_for_delay": "yes",
            "blocks_others": "yes",
            "outcome_value": "high",
            "strategic_alignment": "medium",
            "reversibility": "low",
            "visibility": "medium",
        }

        with patch("cosai_app.logic.extract_task", return_value=mock_extracted):
            results = analyze_messages(messages, prefs={}, memory=[], hint_profile=hint_profile)

        # Only the task-like invoice message should pass filtering into analysis.
        self.assertEqual(len([r for r in results if r.get("status") != "error"]), 1)
        self.assertEqual(results[0]["task"], "Submit invoice to finance")


if __name__ == "__main__":
    unittest.main()
