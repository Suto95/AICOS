# API Contract v1 (Migration Draft)

## Base URL
- Local: `/`
- Versioned prefix: `/v1`

## Authentication
- Initial migration phase: explicit `user_id` path parameter.
- Later phase: replace with authenticated identity from token/session.

Interim frontend-friendly mode is now available:
- Send `X-User-Id: <id>` header and call `/v1/me/*` routes.
- Preferred mode: send `Authorization: Bearer <session_token>` for `/v1/me/*` routes.

### Create Session Token
`POST /v1/auth/session`

Request:
```json
{
  "user_id": 101,
  "email": "user@example.com"
}
```

### Session Introspection
`GET /v1/auth/me`

Headers:
- `Authorization: Bearer <session_token>`

Response:
```json
{
  "user_id": 101,
  "email": "user@example.com",
  "expires_at": 1761600000
}
```

### Session Refresh
`POST /v1/auth/refresh`

Headers:
- `Authorization: Bearer <session_token>`

Response:
```json
{
  "session_token": "new-token",
  "expires_at": 1761605000
}
```

Production note:
- Set `COSAI_SESSION_SECRET` and `COSAI_ENV=production`.

Response:
```json
{
  "session_token": "token",
  "user_id": 101,
  "email": "user@example.com"
}
```

## Endpoints

### Start Google OAuth
`POST /v1/auth/google/start`

Request:
```json
{
  "redirect_uri": "http://localhost:5173/"
}
```

Response:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?...",
  "state": "random-state"
}
```

### Complete Google OAuth
`POST /v1/auth/google/callback`

Request:
```json
{
  "code": "google-code",
  "state": "random-state",
  "redirect_uri": "http://localhost:5173/"
}
```

Response:
```json
{
  "user_id": 101,
  "email": "user@example.com"
}
```

### Health
`GET /health`

Response:
```json
{
  "status": "ok"
}
```

### List Tasks
`GET /v1/users/{user_id}/tasks?include_deleted=false&limit=5000`

Alias:
- `GET /v1/me/tasks` with `X-User-Id` header.

Response:
```json
{
  "items": [
    {
      "id": 10,
      "task": "Finalize release notes",
      "bucket": "DO NOW",
      "status": "open"
    }
  ]
}
```

### Create Manual Task
`POST /v1/users/{user_id}/tasks`

Alias:
- `POST /v1/me/tasks` with `X-User-Id` header.

Request:
```json
{
  "task": "Prepare migration timeline",
  "bucket": "SCHEDULE",
  "source": "manual"
}
```

Response:
```json
{
  "item": {
    "id": 11,
    "task": "Prepare migration timeline",
    "bucket": "SCHEDULE"
  }
}
```

### Update Task Status
`POST /v1/users/{user_id}/tasks/{task_id}/status`

Alias:
- `POST /v1/me/tasks/{task_id}/status` with `X-User-Id` header.

Request:
```json
{
  "status": "done"
}
```

Supported status values:
- `open`
- `done`
- `deleted`

### Analyze Messages
`POST /v1/users/{user_id}/tasks/analyze`

Alias:
- `POST /v1/me/tasks/analyze` with `X-User-Id` header.

Request:
```json
{
  "messages": [
    {
      "subject": "Need final numbers by EOD",
      "snippet": "Please send updated dashboard",
      "body": "...",
      "sender": "manager@example.com",
      "timestamp": "2026-10-20T09:00:00+00:00",
      "thread_id": "abc",
      "message_id": "m1"
    }
  ],
  "account_id": 1,
  "persist": false
}
```

Response:
```json
{
  "items": [
    {
      "task": "Send updated dashboard",
      "bucket": "DO NOW"
    }
  ]
}
```

### Insights Summary
`GET /v1/users/{user_id}/insights/summary`

Alias:
- `GET /v1/me/insights/summary` with `X-User-Id` header.

Response:
```json
{
  "active_tasks": 12,
  "done_tasks": 30,
  "memory_entries": 55,
  "recent_events": 80
}
```

### List Connected Accounts
`GET /v1/users/{user_id}/accounts`

Alias:
- `GET /v1/me/accounts` with `X-User-Id` header.

Response:
```json
{
  "items": [
    {
      "id": 1,
      "provider": "gmail",
      "account_email": "user@example.com",
      "query_filter": "in:inbox category:primary",
      "status": "active"
    }
  ]
}
```

### Update Account Query Filter
`PATCH /v1/users/{user_id}/accounts/{account_id}/query-filter`

Alias:
- `PATCH /v1/me/accounts/{account_id}/query-filter` with `X-User-Id` header.

Request:
```json
{
  "query_filter": "newer_than:7d"
}
```

Response:
```json
{
  "items": [
    {
      "id": 1,
      "query_filter": "newer_than:7d"
    }
  ]
}
```

### Disconnect Account
`POST /v1/users/{user_id}/accounts/{account_id}/disconnect`

Alias:
- `POST /v1/me/accounts/{account_id}/disconnect` with `X-User-Id` header.

Response:
```json
{
  "items": []
}
```

## Error Model
Errors return:
```json
{
  "error": "human readable message"
}
```

HTTP status guidance:
- `400` for invalid request payload.
- `404` when task or user-scoped resource is not found.
- `500` for unexpected failures.