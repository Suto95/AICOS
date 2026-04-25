## v0.10-beta - 2026-04-25

### Added
- Production deployment infrastructure:
  - Database migration script (SQLite → PostgreSQL)
  - Streamlit secrets configuration template
  - GitHub Actions CI/CD workflow
  - Sentry error logging integration
  - Google Analytics usage tracking
  - Comprehensive production deployment guide

### Added
- Per-user production data model using SQLite (`users`, `connected_accounts`, `user_prefs`, `task_memory`, `task_events`, OAuth state cache).
- Account Setup page for connecting and managing Gmail accounts.
- Google-first login flow where `Continue with Google` performs sign-in plus Gmail connection.
- OAuth hardening with PKCE verifier/challenge, callback resilience, and state-verifier cache fallback.
- Token protection with encryption-key based storage (`COSAI_ENCRYPTION_KEY`).
- Account health metadata and on-demand Gmail health checks.
- One-click migration from local files (`user_prefs.json`, `task_memory.jsonl`, `task_events.jsonl`) into user-scoped DB data.
- Cross-user hint learning so new users benefit from historical action/noise patterns.

### Changed
- Rebranded product UI text from **CosAI** to **AICOS**.
- Fetch controls changed from count-based to duration-based windows:
  - Last 3 hours, Last 24 hours, Last 3 days, Last 7 days.
- Default Gmail fetch scope simplified to user-invisible filter:
  - `in:inbox category:primary`
- Scope messaging replaced with user-friendly trust statement.
- Preferences view in System Insights converted to table format and renamed for clarity.
- Removed "Table-first workflow" subheading from Task Board page for cleaner UI.

### Fixed
- Removed legacy hardcoded `subject:cosai test` behavior from fallback fetch path.
- Fixed OAuth loops caused by session resets and missing callback state handling.
- Fixed `invalid_grant Missing code verifier` by persisting and replaying PKCE verifier.
- Fixed OAuth scope mismatch errors by using canonical Google userinfo scopes.
- Added compatibility handling for stale module reload signatures in Streamlit.
- Fixed disconnect account CTA not removing inactive accounts from list.
- Improved Gmail account connection button text: shows "Add Gmail account" when no accounts exist, "Add another Gmail account" when accounts are connected.
- Enhanced OAuth code verifier error handling with explicit validation and helpful error messages.

## v0.8 - 2026-04-20

### Added
- Multipage Streamlit architecture:
  - Home, Task Board, System Insights.
- Modular code split:
  - `config.py`, `data.py`, `logic.py`, `state.py`, `ui.py`, `insights.py`.
- Backward-compatible wrapper entrypoint.

### Changed
- UI shifted to table-first workflow with editable task board and row-level actions.
- Added undo stack support and manual rank ordering.

## v0.7 - 2026-04-20

### Added
- Done suggestion system (retrieval + LLM verifier):
  - Labels: `POTENTIAL_DONE`, `NOT_DONE`, `UNSURE`.
- Event-history-aware verification and user-confirmed completion actions.
- Deduping safeguards:
  - one-best-task-per-message and message-level dedupe.

## v0.6 - 2026-04-20

### Added
- Inference MVP for missing signal completion:
  - memory similarity, sender priors, global priors.
- Long-term memory storage for clarified signals.
- Confidence-threshold based selective auto-fill.

## v0.5 - 2026-04-19

### Added
- Preference learning feedback loop:
  - learns from task behavior and updates scoring weights.
- Event logging pipeline for task lifecycle actions.

## v0.4 - 2026-04-19

### Added
- Adaptive clarification wizard:
  - asks only missing critical signals with validated controls.
- Task reasoning generation action.

## v0.3 - 2026-04-19

### Added
- Action layer:
  - bucket reassignment, mark done/reopen, soft delete with confirmation.
- Manual task creation and persistent status updates.

## v0.2 - 2026-04-18

### Added
- Prioritization engine:
  - urgency and importance feature engineering.
- Bucket mapping:
  - `DO NOW`, `SCHEDULE`, `DELEGATE`, `REVIEW LATER`, `ELIMINATE`.

## v0.1 - 2026-04-18

### Added
- Gmail ingestion pipeline with token refresh support.
- Rich message payload extraction:
  - `subject`, `snippet`, `body`, `full_text`, `sender`, `timestamp`, `thread_id`, `message_id`.
- Initial LLM structured task extraction.
