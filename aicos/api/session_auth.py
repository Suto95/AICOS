import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional


_DEV_FALLBACK_SECRET = "dev-insecure-session-secret-change-me"


def _is_production_env() -> bool:
    env = (os.getenv("COSAI_ENV") or os.getenv("ENV") or "").strip().lower()
    return env in {"prod", "production"}


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _session_secret() -> bytes:
    secret = (os.getenv("COSAI_SESSION_SECRET") or "").strip()
    if not secret:
        if _is_production_env():
            raise RuntimeError("COSAI_SESSION_SECRET is required in production.")
        # Dev fallback only.
        secret = _DEV_FALLBACK_SECRET
    return secret.encode("utf-8")


def create_session_token(user_id: int, email: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    now = int(time.time())
    payload = {
        "uid": int(user_id),
        "email": str(email or ""),
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(_session_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{sig_b64}"


def decode_session_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    payload_b64, sig_b64 = token.split(".", 1)
    expected_sig = hmac.new(_session_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        uid = int(payload.get("uid", 0))
        exp = int(payload.get("exp", 0))
    except Exception:
        return None
    if uid <= 0:
        return None
    if exp <= int(time.time()):
        return None
    return payload


def refresh_session_token(token: str, ttl_seconds: int = 7 * 24 * 3600) -> Optional[str]:
    payload = decode_session_token(token)
    if payload is None:
        return None
    return create_session_token(user_id=int(payload["uid"]), email=str(payload.get("email") or ""), ttl_seconds=ttl_seconds)
