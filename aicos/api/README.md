# AICOS Migration API

This package hosts the initial FastAPI layer used for the React migration.

## Run locally

```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn aicos.api.main:app --reload --port 8000
```

## Endpoints
- `GET /health`
- `POST /v1/auth/session`
- `GET /v1/auth/me`
- `POST /v1/auth/refresh`
- `POST /v1/auth/google/start`
- `POST /v1/auth/google/callback`
- `GET /v1/users/{user_id}/tasks`
- `GET /v1/me/tasks` (requires `X-User-Id` header)
- `POST /v1/users/{user_id}/tasks`
- `POST /v1/me/tasks` (requires `X-User-Id` header)
- `POST /v1/users/{user_id}/tasks/{task_id}/status`
- `POST /v1/me/tasks/{task_id}/status` (requires `X-User-Id` header)
- `POST /v1/users/{user_id}/tasks/analyze`
- `POST /v1/me/tasks/analyze` (requires `X-User-Id` header)
- `GET /v1/users/{user_id}/insights/summary`
- `GET /v1/me/insights/summary` (requires `X-User-Id` header)
- `GET /v1/users/{user_id}/accounts`
- `GET /v1/me/accounts` (requires `X-User-Id` header)
- `PATCH /v1/users/{user_id}/accounts/{account_id}/query-filter`
- `PATCH /v1/me/accounts/{account_id}/query-filter` (requires `X-User-Id` header)
- `POST /v1/users/{user_id}/accounts/{account_id}/disconnect`
- `POST /v1/me/accounts/{account_id}/disconnect` (requires `X-User-Id` header)

## Auth Headers for /v1/me
- Preferred: `Authorization: Bearer <session_token>`
- Backward compatible: `X-User-Id: <id>`

For session verification in frontend bootstrapping:
- `GET /v1/auth/me` with bearer token

For session rotation:
- `POST /v1/auth/refresh` with bearer token

## Production Security
- Set `COSAI_SESSION_SECRET` in production.
- Set `COSAI_ENV=production` (or `ENV=production`) to enforce secret requirement.

Contract details are defined in:
- `docs/migration/api-contract-v1.md`

## Google OAuth Notes
- Add the React callback URL (for example `http://localhost:5173/`) to `COSAI_REDIRECT_URI`.
- Keep existing Streamlit callback URIs in the same comma-separated env var.