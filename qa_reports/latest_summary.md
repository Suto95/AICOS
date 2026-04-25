# AICOS QA Agent Report

- Generated at: `2026-04-25T09:42:27.204112`
- Overall status: **SUCCESS**

## Change Coverage
- Total changelog cases: **40**
- Automated mapped cases: **19**
- Uncovered cases: **21**
- Automated coverage: **47.5%**

## Test Execution (All Suites)
- Tests ran: **13**
- Failures: **0**
- Errors: **0**
- Skipped: **0**

## Suite Breakdown
- **unit** (`tests/aicos`): PASS | Ran: 6 | Failures: 0 | Errors: 0 | Skipped: 0
- **integration** (`tests/aicos_integration`): PASS | Ran: 5 | Failures: 0 | Errors: 0 | Skipped: 0
- **e2e** (`tests/aicos_e2e`): PASS | Ran: 1 | Failures: 0 | Errors: 0 | Skipped: 0
- **bucket_sim** (`tools/simulate_buckets.py`): PASS | Ran: 1 | Failures: 0 | Errors: 0 | Skipped: 0

## Uncovered Change Cases (Needs More Tests)
- [v0.9-beta - 2026-04-21::Added] Account Setup page for connecting and managing Gmail accounts.
- [v0.9-beta - 2026-04-21::Changed] Rebranded product UI text from **CosAI** to **AICOS**.
- [v0.9-beta - 2026-04-21::Changed] Scope messaging replaced with user-friendly trust statement.
- [v0.9-beta - 2026-04-21::Changed] Preferences view in System Insights converted to table format and renamed for clarity.
- [v0.8 - 2026-04-20::Added] Modular code split:
- [v0.8 - 2026-04-20::Added] Backward-compatible wrapper entrypoint.
- [v0.8 - 2026-04-20::Changed] UI shifted to table-first workflow with editable task board and row-level actions.
- [v0.8 - 2026-04-20::Changed] Added undo stack support and manual rank ordering.
- [v0.7 - 2026-04-20::Added] Done suggestion system (retrieval + LLM verifier):
- [v0.7 - 2026-04-20::Added] Deduping safeguards:
- [v0.6 - 2026-04-20::Added] Inference MVP for missing signal completion:
- [v0.6 - 2026-04-20::Added] Long-term memory storage for clarified signals.
- [v0.6 - 2026-04-20::Added] Confidence-threshold based selective auto-fill.
- [v0.5 - 2026-04-19::Added] Preference learning feedback loop:
- [v0.4 - 2026-04-19::Added] Adaptive clarification wizard:
- [v0.4 - 2026-04-19::Added] Task reasoning generation action.
- [v0.3 - 2026-04-19::Added] Action layer:
- [v0.3 - 2026-04-19::Added] Manual task creation and persistent status updates.
- [v0.1 - 2026-04-18::Added] Gmail ingestion pipeline with token refresh support.
- [v0.1 - 2026-04-18::Added] Rich message payload extraction:
- [v0.1 - 2026-04-18::Added] Initial LLM structured task extraction.

## Raw Outputs
### unit (tests/aicos)
```text
test_default_gmail_filter (test_accounts_defaults.TestAccountsDefaults) ... ok
test_load_events_all_users (test_data_events.TestDataEvents) ... ok
test_compact_message_context_truncates_body (test_logic_hints.TestHintLearning) ... ok
test_derive_user_hint_profile_from_events (test_logic_hints.TestHintLearning) ... ok
test_is_task_like_message_uses_hints (test_logic_hints.TestHintLearning) ... ok
test_merge_hint_profiles (test_logic_hints.TestHintLearning) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.015s

OK
```

### integration (tests/aicos_integration)
```text
test_oauth_state_cache_roundtrip (test_accounts_db_flow.TestAccountsDbFlow) ... ok
test_oauth_upsert_and_read_active_account (test_accounts_db_flow.TestAccountsDbFlow) ... ok
test_pending_login_account_creation (test_accounts_db_flow.TestAccountsDbFlow) ... ok
test_encrypt_decrypt_without_key_falls_back_to_plain_prefix (test_security_tokens.TestSecurityTokens) ... ok
test_legacy_plaintext_is_backward_compatible (test_security_tokens.TestSecurityTokens) ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.028s

OK
```

### e2e (tests/aicos_e2e)
```text
test_cross_user_hints_affect_task_like_filtering_and_pipeline (test_e2e_message_pipeline.TestE2EMessagePipeline) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.005s

OK
```

### bucket_sim (tools/simulate_buckets.py)
```text
Bucket simulation summary written to: qa_reports/bucket_sim_summary.md
Bucket simulation json written to: qa_reports/bucket_sim_summary.json
Bucket simulation mismatches written to: qa_reports/bucket_sim_mismatches.jsonl
Status: PASS | filter_accuracy=100.0% | bucket_accuracy=99.41%
```
