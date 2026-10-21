# React Migration 10-Day Low-Intervention Plan

## Goal
Move from Streamlit-first UI to React UI with Python API backend while keeping existing behavior stable and reducing manual intervention to short approval checkpoints.

## Scope for 10-Day Version
- Keep current core logic in Python modules under `aicos/cosai_app`.
- Introduce API layer first, then React UI against that API.
- Preserve Gmail auth/account linking, task extraction, board operations, and insights.
- Avoid non-critical redesign work until after cutover.

## Prerequisites (Day 0)
- Repo access, deployment platform accounts, and DNS access.
- Separate environments: `dev`, `staging`, `prod`.
- Secrets ready for OAuth, DB, LLM provider, and monitoring.
- Confirm PostgreSQL migration sequence reset is included after data import.

## Daily Plan

### Day 1: Baseline and Contracts
- Freeze scope for 10-day migration (MVP parity only).
- Capture current Streamlit flows and data contracts.
- Define API endpoint list and response schemas.
- Create migration branch and CI checks for lint/import/smoke tests.

Approval gate:
- Approve endpoint contract document.

### Day 2: Backend API Skeleton
- Add FastAPI app skeleton and health endpoint.
- Add shared settings and env loading for API service.
- Wire existing auth/account modules behind API service boundaries.
- Add structured error responses and request logging.

Approval gate:
- Confirm API boots in local and staging.

### Day 3: Task and Insights Endpoints
- Expose task list/create/update endpoints.
- Expose insights summary endpoint.
- Add message analysis/task extraction endpoint wrappers.
- Add integration tests for endpoint behavior using fixture data.

Approval gate:
- Sign off on endpoint payloads from sample calls.

### Day 4: React Foundation
- Scaffold React app (preferred: Next.js).
- Add app shell, routing, auth state, and API client.
- Add environment handling for staging/prod API URLs.
- Add error boundary, loading states, and toast notifications.

Approval gate:
- Confirm login and base navigation in staging frontend.

### Day 5: Account Setup + Auth Flow
- Implement account connection screen and OAuth callbacks.
- Implement secure token/session handling.
- Validate redirect URI behavior for staging and production domains.

Approval gate:
- Complete end-to-end account link test in staging.

### Day 6: Task Board UI
- Implement task board columns, sorting, and status changes.
- Connect create/edit/status actions to API.
- Add optimistic UI updates and retry on transient failures.

Approval gate:
- Task board parity test against Streamlit behavior passes.

### Day 7: Insights and Preferences
- Implement insights dashboard with existing metrics.
- Implement preferences/settings UI.
- Verify archived learning preference behavior remains unchanged.

Approval gate:
- Insights numbers validated against baseline dataset.

### Day 8: Hardening and Background Jobs
- Add API rate limit and auth middleware checks.
- Validate ingestion/background workflows and error handling.
- Add monitoring hooks (Sentry/log correlation IDs).

Approval gate:
- Error alerts verified with one forced-failure test.

### Day 9: Staging Soak + Cutover Rehearsal
- Run full regression suite in staging.
- Perform cutover rehearsal including rollback drill.
- Validate DB backups and restore test.

Approval gate:
- Go/no-go decision for production launch.

### Day 10: Production Cutover
- Deploy frontend and backend production releases.
- Enable traffic gradually (canary if available).
- Watch metrics and logs for first 2-4 hours.
- Keep old Streamlit path available for rollback window.

Approval gate:
- Final acceptance after smoke checks and monitoring stability.

## Minimal Manual Interventions
- Five short approvals only: Day 1, 3, 5, 9, 10.
- Everything else can be automated by CI, scripts, and deployment pipelines.

## Risks and Mitigations
- OAuth mismatch across environments.
  - Mitigation: pre-register exact callback URIs per environment.
- PostgreSQL migration sequence mismatch after import.
  - Mitigation: run sequence reset step after migration.
- Hidden coupling between Streamlit state and business logic.
  - Mitigation: isolate service layer before React wiring.
- LLM-provider drift in extraction outputs.
  - Mitigation: fixture-based regression checks in CI.

## Exit Criteria
- All MVP user flows work in React UI against Python API.
- CI green on unit/integration/smoke checks.
- Monitoring and alerting live before 100% traffic.
- Rollback procedure tested and documented.

## Local Dev Quickstart (Current Implementation)

Run API:

```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn aicos.api.main:app --reload --port 8000
```

Run React UI:

```bash
cd web
npm install
npm run dev
```

Optional frontend env in `web/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```