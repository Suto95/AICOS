import unittest

from cosai_app.logic import (
    build_compact_message_context,
    compute_features,
    derive_user_hint_profile,
    is_task_like_message,
    merge_hint_profiles,
    normalize_task,
)


class TestHintLearning(unittest.TestCase):
    def test_derive_user_hint_profile_from_events(self):
        events = [
            {"event_type": "task_created_manual", "task_text": "Review invoice and submit reimbursement", "payload": {"account_id": 1}},
            {"event_type": "task_created_manual", "task_text": "Submit monthly invoice now", "payload": {"account_id": 1}},
            {"event_type": "task_deleted", "task_text": "newsletter promotion sale discount", "payload": {"account_id": 1, "source": "email", "sender_domain": "promo.example.com"}},
            {"event_type": "task_deleted", "task_text": "weekly newsletter discount promo", "payload": {"account_id": 1, "source": "email", "sender_domain": "promo.example.com"}},
        ]
        profile = derive_user_hint_profile(events, account_id=1)
        self.assertIn("invoice", profile["action_tokens"])
        self.assertIn("newsletter", profile["noise_tokens"])
        self.assertIn("promo.example.com", profile["noise_sender_domains"])

    def test_merge_hint_profiles(self):
        a = {"action_tokens": {"invoice"}, "noise_tokens": {"promo"}, "noise_sender_domains": {"a.com"}}
        b = {"action_tokens": {"deadline"}, "noise_tokens": {"discount"}, "noise_sender_domains": {"b.com"}}
        merged = merge_hint_profiles(a, b)
        self.assertEqual(merged["action_tokens"], {"invoice", "deadline"})
        self.assertEqual(merged["noise_tokens"], {"promo", "discount"})
        self.assertEqual(merged["noise_sender_domains"], {"a.com", "b.com"})

    def test_is_task_like_message_uses_hints(self):
        hint_profile = {
            "action_tokens": {"invoice"},
            "noise_tokens": {"newsletter", "discount"},
            "noise_sender_domains": {"noise.example.com"},
        }
        action_msg = {"subject": "Invoice review needed", "snippet": "please submit by tomorrow", "sender": "ops@example.com"}
        noise_msg = {"subject": "Weekly newsletter discount", "snippet": "big promo", "sender": "ads@noise.example.com"}
        self.assertTrue(is_task_like_message(action_msg, hint_profile=hint_profile))
        self.assertFalse(is_task_like_message(noise_msg, hint_profile=hint_profile))

    def test_compact_message_context_truncates_body(self):
        msg = {
            "subject": "Action Required",
            "sender": "lead@example.com",
            "snippet": "Please update",
            "body": "x" * 2000,
        }
        compact = build_compact_message_context(msg, max_body_chars=120)
        self.assertIn("Subject: Action Required", compact)
        self.assertIn("From: lead@example.com", compact)
        body_line = [line for line in compact.splitlines() if line.startswith("Body: ")]
        self.assertTrue(body_line)
        self.assertLessEqual(len(body_line[0]) - len("Body: "), 120)

    def test_normalize_task_lowercases_external_signals(self):
        task = {
            "deadline": "2026-12-01",
            "urgency_signal": "High",
            "importance_signal": "MEDIUM",
        }
        normalized = normalize_task(task)
        self.assertEqual(normalized["urgency_signal"], "high")
        self.assertEqual(normalized["importance_signal"], "medium")

    def test_compute_features_applies_signal_overrides(self):
        task_without_signal = {
            "deadline": "2026-12-01",
            "penalty_for_delay": "no",
            "blocks_others": "no",
            "outcome_value": "medium",
            "strategic_alignment": "medium",
            "reversibility": "medium",
            "visibility": "medium",
        }
        task_with_signal = task_without_signal.copy()
        task_with_signal["urgency_signal"] = "high"
        task_with_signal["importance_signal"] = "high"

        urgency_base, importance_base = compute_features(task_without_signal, prefs={})
        urgency_signal, importance_signal = compute_features(task_with_signal, prefs={})

        self.assertGreater(urgency_signal, urgency_base)
        self.assertGreater(importance_signal, importance_base)


if __name__ == "__main__":
    unittest.main()
