# Migration Requirements Checklist

Use this checklist to control scope and avoid regressions during the React migration.

## Functional Requirements
- [ ] User authentication and session persistence work in React UI.
- [ ] OAuth account linking and reconnect flows succeed.
- [ ] Task ingestion, extraction, and categorization outputs remain compatible.
- [ ] Task board supports view, create, update, and status transitions.
- [ ] Insights dashboard metrics match baseline calculations.
- [ ] User preferences can be read and updated.

## Data and Database Requirements
- [ ] PostgreSQL schema is migrated and validated.
- [ ] Sequence reset is performed after bulk import.
- [ ] Backup and restore test has been completed.
- [ ] Data retention and audit requirements are documented.

## Security Requirements
- [ ] Secrets are stored only in environment/secrets manager.
- [ ] HTTPS is enforced for all public endpoints.
- [ ] CORS policy is explicit and environment-specific.
- [ ] Session/JWT handling includes expiry and refresh controls.
- [ ] Logs redact secrets and sensitive user data.

## Reliability Requirements
- [ ] Health endpoints exist for frontend and backend.
- [ ] Retries and timeouts are configured for external dependencies.
- [ ] Background jobs are idempotent where required.
- [ ] Alerting exists for auth failures, API 5xx spikes, and ingestion errors.

## Performance Requirements
- [ ] API read endpoints meet target latency in staging.
- [ ] React bundles are optimized and lazy-loaded where useful.
- [ ] First meaningful paint on main dashboard is acceptable on mobile.

## Delivery and Operations Requirements
- [ ] CI runs lint, tests, and smoke checks on PRs.
- [ ] Staging deployment is automatic from mainline branch.
- [ ] Production deployment includes rollback instructions.
- [ ] Release notes are updated for migration changes.

## Acceptance Criteria
- [ ] All critical flows pass end-to-end tests in staging.
- [ ] Production smoke test passes immediately after cutover.
- [ ] No blocker severity incidents in first 24 hours.