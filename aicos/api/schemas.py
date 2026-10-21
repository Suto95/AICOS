from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str = "ok"


class MessageIn(BaseModel):
    subject: str = ""
    snippet: str = ""
    body: str = ""
    sender: str = ""
    timestamp: str = ""
    thread_id: str = ""
    message_id: str = ""
    text: str = ""
    full_text: str = ""


class AiSettingsIn(BaseModel):
    provider: Optional[str] = None
    primary_model: Optional[str] = None
    fallback_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    use_env_fallback: Optional[bool] = None


class AnalyzeRequest(BaseModel):
    messages: List[MessageIn] = Field(default_factory=list)
    account_id: Optional[int] = None
    persist: bool = False
    ai_settings: Optional[AiSettingsIn] = None


class TaskCreateRequest(BaseModel):
    task: str
    bucket: str = "REVIEW LATER"
    source: str = "manual"


class TaskStatusRequest(BaseModel):
    status: Literal["open", "done", "deleted"]


class TaskListResponse(BaseModel):
    items: List[Dict[str, Any]]


class TaskItemResponse(BaseModel):
    item: Dict[str, Any]


class AnalyzeResponse(BaseModel):
    items: List[Dict[str, Any]]


class InsightsSummaryResponse(BaseModel):
    active_tasks: int
    done_tasks: int
    memory_entries: int
    recent_events: int


class AccountListResponse(BaseModel):
    items: List[Dict[str, Any]]


class AccountQueryFilterRequest(BaseModel):
    query_filter: str


class GoogleAuthStartRequest(BaseModel):
    redirect_uri: Optional[str] = None


class GoogleAuthStartResponse(BaseModel):
    auth_url: str
    state: str


class GoogleAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: Optional[str] = None


class GoogleAuthCallbackResponse(BaseModel):
    user_id: int
    email: str
    session_token: Optional[str] = None


class SessionExchangeRequest(BaseModel):
    user_id: int
    email: str = ""


class SessionExchangeResponse(BaseModel):
    session_token: str
    user_id: int
    email: str


class SessionMeResponse(BaseModel):
    user_id: int
    email: str
    expires_at: int


class SessionRefreshResponse(BaseModel):
    session_token: str
    expires_at: int