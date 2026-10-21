import os
from datetime import datetime
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from aicos.cosai_app.config import BUCKET_ORDER
from aicos.cosai_app.accounts import (
    DEFAULT_GMAIL_QUERY_FILTER,
    build_google_auth_url,
    cache_oauth_verifier,
    complete_google_oauth,
    ensure_login_email_account,
    disconnect_account,
    list_connected_accounts,
    pop_oauth_verifier,
    get_active_account,
    upsert_google_account,
    update_account_fetch_success,
    update_account_health,
    update_account_tokens,
    update_account_query_filter,
)
from aicos.cosai_app import gmail_ingest
from aicos.cosai_app.data import (
    append_event,
    load_events,
    load_events_all_users,
    load_ai_settings,
    load_memory,
    load_persisted_tasks,
    load_prefs,
    save_ai_settings,
)
from aicos.cosai_app.db import get_conn, init_db
from aicos.cosai_app.logic import (
    analyze_messages,
    derive_user_hint_profile,
    merge_hint_profiles,
    score_task,
)

from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    FetchAnalyzeRequest,
    FetchAnalyzeResponse,
    AiSettingsResponse,
    AiSettingsUpdateRequest,
    AccountListResponse,
    AccountQueryFilterRequest,
    ApiError,
    GoogleAuthCallbackRequest,
    GoogleAuthCallbackResponse,
    GoogleAuthStartRequest,
    GoogleAuthStartResponse,
    SessionMeResponse,
    SessionRefreshResponse,
    SessionExchangeRequest,
    SessionExchangeResponse,
    HealthResponse,
    InsightsSummaryResponse,
    TaskCreateRequest,
    TaskItemResponse,
    TaskListResponse,
    TaskStatusRequest,
)
from .session_auth import create_session_token, decode_session_token, refresh_session_token


app = FastAPI(title="AICOS Migration API", version="0.1.0")

DURATION_OPTIONS = {
    "Last 3 hours": timedelta(hours=3),
    "Last 24 hours": timedelta(hours=24),
    "Last 3 days": timedelta(days=3),
    "Last 7 days": timedelta(days=7),
}


@app.on_event("startup")
def initialize_database() -> None:
    init_db()


def _allowed_origins() -> List[str]:
    raw = (os.getenv("COSAI_API_CORS_ORIGINS") or "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_dict_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows or []]


def _require_user_id(x_user_id: Optional[str], authorization: Optional[str]) -> int:
    payload = _require_bearer_payload(authorization)
    if payload is not None:
        return int(payload["uid"])

    raw = (x_user_id or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")
    try:
        user_id = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-User-Id header") from exc
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="X-User-Id must be positive")
    return user_id


def _require_bearer_payload(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    auth = (authorization or "").strip()
    if not auth:
        return None
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer token")
    token = auth[7:].strip()
    payload = decode_session_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return payload


def _task_event_payload(task: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(extra or {})
    payload["task_snapshot"] = {
        "id": task.get("id"),
        "task": task.get("task", ""),
        "score": task.get("score", 0),
        "bucket": task.get("bucket", "REVIEW LATER"),
        "predicted_bucket": task.get("predicted_bucket", task.get("bucket", "REVIEW LATER")),
        "reason": task.get("reason", []),
        "meta": task.get("meta", {}),
        "inferred": task.get("inferred", {}),
        "status": task.get("status", "open"),
        "manual_override": task.get("manual_override", False),
        "override_comment": task.get("override_comment", ""),
        "source": task.get("source", ""),
        "created_at": task.get("created_at", ""),
        "updated_at": task.get("updated_at", ""),
    }
    if task.get("manual_rank") is not None:
        payload["task_snapshot"]["manual_rank"] = task.get("manual_rank")
    return payload


def _filter_messages_by_duration(messages: List[Dict[str, Any]], window: timedelta) -> List[Dict[str, Any]]:
    now = datetime.now().astimezone()
    cutoff = now - window
    filtered: List[Dict[str, Any]] = []
    for msg in messages:
        raw_ts = msg.get("timestamp", "")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=now.tzinfo)
        if ts >= cutoff:
            filtered.append(msg)
    return filtered


def _find_or_create_user(email: str) -> Dict[str, Any]:
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        raise HTTPException(status_code=400, detail="Google account did not return a valid email")

    init_db()
    now = datetime.now().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT id, email FROM users WHERE email = ?", (normalized,)).fetchone()
        if row:
            return {"id": int(row["id"]), "email": row["email"]}
        cur = conn.execute("INSERT INTO users(email, created_at) VALUES(?, ?)", (normalized, now))
        conn.commit()
        return {"id": int(cur.lastrowid), "email": normalized}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/v1/auth/session",
    response_model=SessionExchangeResponse,
    responses={400: {"model": ApiError}},
)
def create_session(req: SessionExchangeRequest) -> SessionExchangeResponse:
    user_id = int(req.user_id)
    email = (req.email or "").strip().lower()
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id must be positive")
    token = create_session_token(user_id=user_id, email=email)
    return SessionExchangeResponse(session_token=token, user_id=user_id, email=email)


@app.get(
    "/v1/auth/me",
    response_model=SessionMeResponse,
    responses={401: {"model": ApiError}},
)
def session_me(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> SessionMeResponse:
    payload = _require_bearer_payload(authorization)
    if payload is None:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")
    return SessionMeResponse(
        user_id=int(payload["uid"]),
        email=str(payload.get("email") or ""),
        expires_at=int(payload["exp"]),
    )


@app.post(
    "/v1/auth/refresh",
    response_model=SessionRefreshResponse,
    responses={401: {"model": ApiError}},
)
def refresh_session(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> SessionRefreshResponse:
    payload = _require_bearer_payload(authorization)
    if payload is None:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")

    token = (authorization or "").strip()[7:].strip()
    refreshed = refresh_session_token(token)
    if not refreshed:
        raise HTTPException(status_code=401, detail="Unable to refresh session token")

    refreshed_payload = decode_session_token(refreshed)
    if refreshed_payload is None:
        raise HTTPException(status_code=401, detail="Unable to refresh session token")

    return SessionRefreshResponse(session_token=refreshed, expires_at=int(refreshed_payload["exp"]))


@app.post(
    "/v1/auth/google/start",
    response_model=GoogleAuthStartResponse,
    responses={500: {"model": ApiError}},
)
def start_google_auth(req: GoogleAuthStartRequest) -> GoogleAuthStartResponse:
    try:
        auth_url, state, code_verifier = build_google_auth_url(redirect_uri=req.redirect_uri)
        cache_oauth_verifier(user_id=0, state=state, code_verifier=code_verifier)
        return GoogleAuthStartResponse(auth_url=auth_url, state=state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to start Google OAuth: {exc}") from exc


@app.post(
    "/v1/auth/google/callback",
    response_model=GoogleAuthCallbackResponse,
    responses={400: {"model": ApiError}, 500: {"model": ApiError}},
)
def finish_google_auth(req: GoogleAuthCallbackRequest) -> GoogleAuthCallbackResponse:
    code = (req.code or "").strip()
    state = (req.state or "").strip()
    if not code or not state:
        raise HTTPException(status_code=400, detail="code and state are required")

    verifier = pop_oauth_verifier(user_id=0, state=state)
    if not verifier:
        raise HTTPException(status_code=400, detail="OAuth state expired or invalid")

    try:
        token_payload = complete_google_oauth(
            code=code,
            state=state,
            redirect_uri=req.redirect_uri,
            code_verifier=verifier,
        )
        user = _find_or_create_user(token_payload.get("account_email", ""))
        ensure_login_email_account(user["id"], user["email"])
        upsert_google_account(user["id"], token_payload)
        token = create_session_token(user_id=user["id"], email=user["email"])
        return GoogleAuthCallbackResponse(user_id=user["id"], email=user["email"], session_token=token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google OAuth callback failed: {exc}") from exc


@app.get(
    "/v1/users/{user_id}/tasks",
    response_model=TaskListResponse,
    responses={500: {"model": ApiError}},
)
def list_tasks(user_id: int, include_deleted: bool = False, limit: int = 5000) -> TaskListResponse:
    try:
        rows = load_persisted_tasks(user_id=user_id, limit=limit)
        if not include_deleted:
            rows = [r for r in rows if r.get("status") != "deleted"]
        return TaskListResponse(items=_to_dict_list(rows))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load tasks: {exc}") from exc


@app.get(
    "/v1/me/tasks",
    response_model=TaskListResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def list_my_tasks(
    include_deleted: bool = False,
    limit: int = 5000,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> TaskListResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return list_tasks(user_id=user_id, include_deleted=include_deleted, limit=limit)


@app.post(
    "/v1/users/{user_id}/tasks",
    response_model=TaskItemResponse,
    responses={400: {"model": ApiError}, 500: {"model": ApiError}},
)
def create_manual_task(user_id: int, req: TaskCreateRequest) -> TaskItemResponse:
    task_text = req.task.strip()
    if not task_text:
        raise HTTPException(status_code=400, detail="task is required")

    bucket = req.bucket if req.bucket in BUCKET_ORDER else "REVIEW LATER"
    try:
        existing = load_persisted_tasks(user_id=user_id)
        next_id = max((r.get("id", -1) for r in existing), default=-1) + 1
        prefs = load_prefs(user_id=user_id)
        score, predicted_bucket, reason = score_task({"task": task_text}, prefs)
        now = datetime.now().isoformat()
        task = {
            "id": next_id,
            "task": task_text,
            "score": score,
            "bucket": bucket,
            "predicted_bucket": predicted_bucket,
            "reason": reason,
            "meta": {"task": task_text},
            "inferred": {},
            "status": "open",
            "manual_override": True,
            "override_comment": "",
            "source": req.source,
            "created_at": now,
            "updated_at": now,
        }
        append_event(
            "task_created_manual",
            task["id"],
            task["task"],
            _task_event_payload(task, {"bucket": bucket, "source": req.source}),
            user_id=user_id,
        )
        return TaskItemResponse(item=task)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create task: {exc}") from exc


@app.post(
    "/v1/me/tasks",
    response_model=TaskItemResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def create_my_task(
    req: TaskCreateRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> TaskItemResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return create_manual_task(user_id=user_id, req=req)


@app.post(
    "/v1/users/{user_id}/tasks/{task_id}/status",
    response_model=TaskItemResponse,
    responses={404: {"model": ApiError}, 500: {"model": ApiError}},
)
def update_task_status(user_id: int, task_id: int, req: TaskStatusRequest) -> TaskItemResponse:
    try:
        rows = load_persisted_tasks(user_id=user_id)
        task = next((r for r in rows if int(r.get("id", -1)) == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        now = datetime.now().isoformat()
        if req.status == "done":
            task["status"] = "done"
            event_type = "task_marked_done"
        elif req.status == "deleted":
            task["status"] = "deleted"
            event_type = "task_deleted"
        else:
            task["status"] = "open"
            event_type = "task_reopened"

        task["updated_at"] = now
        append_event(
            event_type,
            task["id"],
            task.get("task", ""),
            _task_event_payload(task, {"status": req.status}),
            user_id=user_id,
        )
        return TaskItemResponse(item=dict(task))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update task: {exc}") from exc


@app.post(
    "/v1/me/tasks/{task_id}/status",
    response_model=TaskItemResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 404: {"model": ApiError}, 500: {"model": ApiError}},
)
def update_my_task_status(
    task_id: int,
    req: TaskStatusRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> TaskItemResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return update_task_status(user_id=user_id, task_id=task_id, req=req)


@app.post(
    "/v1/users/{user_id}/tasks/analyze",
    response_model=AnalyzeResponse,
    responses={400: {"model": ApiError}, 500: {"model": ApiError}},
)
def analyze(user_id: int, req: AnalyzeRequest) -> AnalyzeResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    try:
        prefs = load_prefs(user_id=user_id)
        memory = load_memory(user_id=user_id)
        user_events = load_events(limit=1000, user_id=user_id)
        global_events = load_events_all_users(limit=5000, exclude_user_id=user_id)
        user_hint = derive_user_hint_profile(user_events, account_id=req.account_id)
        global_hint = derive_user_hint_profile(global_events)
        hint_profile = merge_hint_profiles(user_hint, global_hint)

        ai_settings = dict(req.ai_settings.model_dump(exclude_none=True)) if req.ai_settings else None
        rows = analyze_messages(
            [m.model_dump() for m in req.messages],
            prefs,
            memory,
            hint_profile=hint_profile,
            ai_settings=ai_settings,
        )
        rows = _to_dict_list(rows)

        if req.persist:
            current_tasks = load_persisted_tasks(user_id=user_id)
            next_id = max((r.get("id", -1) for r in current_tasks), default=-1) + 1
            for row in rows:
                row["id"] = next_id
                next_id += 1
                append_event(
                    "task_imported_email",
                    row["id"],
                    row.get("task", ""),
                    _task_event_payload(row, {"source": "email", "bucket": row.get("bucket")}),
                    user_id=user_id,
                )

        return AnalyzeResponse(items=rows)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analyze failed: {exc}") from exc


@app.post(
    "/v1/me/tasks/analyze",
    response_model=AnalyzeResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def analyze_my_messages(
    req: AnalyzeRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AnalyzeResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return analyze(user_id=user_id, req=req)


@app.post(
    "/v1/me/tasks/fetch-analyze",
    response_model=FetchAnalyzeResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def fetch_and_analyze_my_messages(
    req: FetchAnalyzeRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> FetchAnalyzeResponse:
    user_id = _require_user_id(x_user_id, authorization)

    try:
        account_id = req.account_id
        if account_id is None:
            active = [a for a in list_connected_accounts(user_id) if a.get("status") == "active"]
            if not active:
                raise HTTPException(status_code=400, detail="No active Gmail account connected")
            account_id = int(active[0]["id"])

        account = get_active_account(user_id, int(account_id))
        if not account:
            raise HTTPException(status_code=400, detail="Selected account is not active")

        window = DURATION_OPTIONS.get(req.duration_label, DURATION_OPTIONS["Last 24 hours"])
        query_filter = (account.get("query_filter") or DEFAULT_GMAIL_QUERY_FILTER).strip()
        effective_query = query_filter
        used_fallback_query = False

        fetch_connected = getattr(gmail_ingest, "fetch_emails_for_account", None)
        if fetch_connected is None:
            raise HTTPException(status_code=500, detail="Gmail fetch integration is unavailable")

        messages, refreshed = fetch_connected(
            account=account,
            max_results=200,
            query=query_filter,
        )
        if not messages and query_filter == DEFAULT_GMAIL_QUERY_FILTER:
            effective_query = "newer_than:30d"
            messages, refreshed = fetch_connected(
                account=account,
                max_results=200,
                query=effective_query,
            )
            used_fallback_query = True

        pre_window_count = len(messages)
        messages = _filter_messages_by_duration(messages, window)
        post_window_count = len(messages)

        update_account_tokens(
            user_id=user_id,
            account_id=int(account_id),
            access_token=refreshed.get("access_token", account.get("access_token", "")),
            refresh_token=refreshed.get("refresh_token", account.get("refresh_token", "")),
            token_expiry=refreshed.get("token_expiry", account.get("token_expiry", "")),
        )
        update_account_fetch_success(user_id, int(account_id))

        prefs = load_prefs(user_id=user_id)
        memory = load_memory(user_id=user_id)
        user_events = load_events(limit=1000, user_id=user_id)
        global_events = load_events_all_users(limit=5000, exclude_user_id=user_id)
        user_hint = derive_user_hint_profile(user_events, account_id=int(account_id))
        global_hint = derive_user_hint_profile(global_events)
        hint_profile = merge_hint_profiles(user_hint, global_hint)

        ai_settings = dict(req.ai_settings.model_dump(exclude_none=True)) if req.ai_settings else load_ai_settings(user_id)
        rows = analyze_messages(
            messages,
            prefs,
            memory,
            hint_profile=hint_profile,
            ai_settings=ai_settings,
        )
        rows = _to_dict_list(rows)

        if req.persist:
            current_tasks = load_persisted_tasks(user_id=user_id)
            next_id = max((r.get("id", -1) for r in current_tasks), default=-1) + 1
            for row in rows:
                row["id"] = next_id
                next_id += 1
                append_event(
                    "task_imported_email",
                    row["id"],
                    row.get("task", ""),
                    _task_event_payload(row, {"source": "email", "bucket": row.get("bucket"), "account_id": int(account_id)}),
                    user_id=user_id,
                )

        return FetchAnalyzeResponse(
            items=rows,
            pre_window_count=pre_window_count,
            post_window_count=post_window_count,
            used_fallback_query=used_fallback_query,
            effective_query=effective_query,
        )
    except HTTPException:
        raise
    except Exception as exc:
        account_id = req.account_id
        if account_id is not None:
            try:
                update_account_health(user_id, int(account_id), status="error", error_msg=str(exc))
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Fetch/analyze failed: {exc}") from exc


@app.get(
    "/v1/me/ai-settings",
    response_model=AiSettingsResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}},
)
def get_my_ai_settings(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AiSettingsResponse:
    user_id = _require_user_id(x_user_id, authorization)
    settings = load_ai_settings(user_id)
    return AiSettingsResponse(**settings)


@app.put(
    "/v1/me/ai-settings",
    response_model=AiSettingsResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def update_my_ai_settings(
    req: AiSettingsUpdateRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AiSettingsResponse:
    user_id = _require_user_id(x_user_id, authorization)
    try:
        save_ai_settings(
            user_id=user_id,
            provider=req.provider,
            primary_model=req.primary_model,
            fallback_model=req.fallback_model,
            api_key=req.api_key,
            base_url=req.base_url,
            use_env_fallback=req.use_env_fallback,
        )
        return AiSettingsResponse(**load_ai_settings(user_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update AI settings: {exc}") from exc


@app.get(
    "/v1/users/{user_id}/insights/summary",
    response_model=InsightsSummaryResponse,
    responses={500: {"model": ApiError}},
)
def insights_summary(user_id: int) -> InsightsSummaryResponse:
    try:
        tasks = load_persisted_tasks(user_id=user_id)
        memory = load_memory(user_id=user_id)
        events = load_events(limit=300, user_id=user_id)
        active_tasks = len([t for t in tasks if t.get("status", "open") == "open"])
        done_tasks = len([t for t in tasks if t.get("status") == "done"])
        return InsightsSummaryResponse(
            active_tasks=active_tasks,
            done_tasks=done_tasks,
            memory_entries=len(memory),
            recent_events=len(events),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load insights summary: {exc}") from exc


@app.get(
    "/v1/me/insights/summary",
    response_model=InsightsSummaryResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def my_insights_summary(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> InsightsSummaryResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return insights_summary(user_id=user_id)


@app.get(
    "/v1/users/{user_id}/accounts",
    response_model=AccountListResponse,
    responses={500: {"model": ApiError}},
)
def list_accounts(user_id: int) -> AccountListResponse:
    try:
        rows = list_connected_accounts(user_id)
        return AccountListResponse(items=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load accounts: {exc}") from exc


@app.get(
    "/v1/me/accounts",
    response_model=AccountListResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def list_my_accounts(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AccountListResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return list_accounts(user_id=user_id)


@app.patch(
    "/v1/users/{user_id}/accounts/{account_id}/query-filter",
    response_model=AccountListResponse,
    responses={400: {"model": ApiError}, 500: {"model": ApiError}},
)
def update_query_filter(user_id: int, account_id: int, req: AccountQueryFilterRequest) -> AccountListResponse:
    query_filter = (req.query_filter or "").strip()
    if not query_filter:
        raise HTTPException(status_code=400, detail="query_filter is required")

    try:
        update_account_query_filter(user_id=user_id, account_id=account_id, query_filter=query_filter)
        rows = list_connected_accounts(user_id)
        return AccountListResponse(items=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update account query filter: {exc}") from exc


@app.patch(
    "/v1/me/accounts/{account_id}/query-filter",
    response_model=AccountListResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def update_my_query_filter(
    account_id: int,
    req: AccountQueryFilterRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AccountListResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return update_query_filter(user_id=user_id, account_id=account_id, req=req)


@app.post(
    "/v1/users/{user_id}/accounts/{account_id}/disconnect",
    response_model=AccountListResponse,
    responses={500: {"model": ApiError}},
)
def disconnect(user_id: int, account_id: int) -> AccountListResponse:
    try:
        disconnect_account(user_id=user_id, account_id=account_id)
        rows = list_connected_accounts(user_id)
        return AccountListResponse(items=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect account: {exc}") from exc


@app.post(
    "/v1/me/accounts/{account_id}/disconnect",
    response_model=AccountListResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 500: {"model": ApiError}},
)
def disconnect_my_account(
    account_id: int,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AccountListResponse:
    user_id = _require_user_id(x_user_id, authorization)
    return disconnect(user_id=user_id, account_id=account_id)