import os
import secrets
import hashlib
import base64
from datetime import datetime

from .db import get_conn, init_db
from .security import decrypt_secret, encrypt_secret

GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
DEFAULT_GMAIL_QUERY_FILTER = "in:inbox category:primary"


def list_connected_accounts(user_id):
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, provider, account_email, scopes, token_expiry, query_filter, status,
                   health_status, health_error, last_health_check_at, last_fetched_at
            FROM connected_accounts
            WHERE user_id = ? AND status != 'inactive'
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def cache_oauth_verifier(user_id, state, code_verifier):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO oauth_state_cache(state, user_id, code_verifier, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (state, user_id, code_verifier, now),
        )
        conn.commit()


def pop_oauth_verifier(user_id, state):
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT code_verifier
            FROM oauth_state_cache
            WHERE state = ? AND user_id = ?
            """,
            (state, user_id),
        ).fetchone()
        if row:
            code_verifier = row["code_verifier"]
            conn.execute("DELETE FROM oauth_state_cache WHERE state = ? AND user_id = ?", (state, user_id))
            conn.commit()
            return code_verifier
    return None


def ensure_login_email_account(user_id, email):
    """
    Ensure the login email appears in connected accounts as a pending Gmail account.
    This gives users a prefilled setup target before OAuth completes.
    """
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        return None

    init_db()
    now = datetime.now().isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM connected_accounts
            WHERE user_id = ? AND provider = 'gmail' AND account_email = ?
            """,
            (user_id, normalized),
        ).fetchone()
        if existing:
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO connected_accounts(
                user_id, provider, account_email, scopes, access_token, refresh_token, token_expiry,
                query_filter, status, health_status, health_error, last_health_check_at, last_fetched_at, created_at, updated_at
            ) VALUES (?, 'gmail', ?, '', '', '', '', ?, 'pending_auth', 'unknown', '', '', '', ?, ?)
            """,
            (user_id, normalized, DEFAULT_GMAIL_QUERY_FILTER, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def upsert_google_account(user_id, token_payload):
    init_db()
    now = datetime.now().isoformat()
    account_email = token_payload.get("account_email", "")
    scopes = " ".join(token_payload.get("scopes", []))
    access_token = encrypt_secret(token_payload.get("access_token", ""))
    refresh_token = encrypt_secret(token_payload.get("refresh_token", ""))
    token_expiry = token_payload.get("token_expiry", "")

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM connected_accounts
            WHERE user_id = ? AND provider = 'gmail' AND account_email = ?
            """,
            (user_id, account_email),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE connected_accounts
                SET scopes = ?, access_token = ?, refresh_token = ?, token_expiry = ?, status = 'active', updated_at = ?
                WHERE id = ?
                """,
                (scopes, access_token, refresh_token, token_expiry, now, int(row["id"])),
            )
            conn.commit()
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO connected_accounts(
                user_id, provider, account_email, scopes, access_token, refresh_token, token_expiry, query_filter, status, created_at, updated_at
            ) VALUES (?, 'gmail', ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                user_id,
                account_email,
                scopes,
                access_token,
                refresh_token,
                token_expiry,
                DEFAULT_GMAIL_QUERY_FILTER,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_account_query_filter(user_id, account_id, query_filter):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE connected_accounts
            SET query_filter = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (query_filter.strip(), now, account_id, user_id),
        )
        conn.commit()


def disconnect_account(user_id, account_id):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE connected_accounts
            SET status = 'inactive', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now, account_id, user_id),
        )
        conn.commit()


def update_account_tokens(user_id, account_id, access_token, refresh_token, token_expiry):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE connected_accounts
            SET access_token = ?, refresh_token = ?, token_expiry = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (encrypt_secret(access_token), encrypt_secret(refresh_token), token_expiry, now, account_id, user_id),
        )
        conn.commit()


def update_account_fetch_success(user_id, account_id):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE connected_accounts
            SET last_fetched_at = ?, health_status = 'healthy', health_error = '', last_health_check_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now, now, now, account_id, user_id),
        )
        conn.commit()


def update_account_health(user_id, account_id, status, error_msg=""):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE connected_accounts
            SET health_status = ?, health_error = ?, last_health_check_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, (error_msg or "")[:500], now, now, account_id, user_id),
        )
        conn.commit()


def get_active_account(user_id, account_id):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM connected_accounts
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (account_id, user_id),
        ).fetchone()
    if not row:
        return None
    acct = dict(row)
    if not (acct.get("query_filter") or "").strip():
        acct["query_filter"] = DEFAULT_GMAIL_QUERY_FILTER
    acct["access_token"] = decrypt_secret(acct.get("access_token", ""))
    acct["refresh_token"] = decrypt_secret(acct.get("refresh_token", ""))
    return acct


def _load_google_oauth_deps():
    try:
        from google_auth_oauthlib.flow import Flow
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Google OAuth dependencies. Install: pip install google-auth google-auth-oauthlib google-api-python-client"
        ) from exc
    return Flow


def _redirect_uris():
    raw = os.getenv("COSAI_REDIRECT_URI", "").strip()
    if not raw:
        return []
    return [uri.strip() for uri in raw.split(",") if uri.strip()]


def _selected_redirect_uri():
    uris = _redirect_uris()
    if not uris:
        raise RuntimeError("Set COSAI_REDIRECT_URI for Google OAuth.")

    base_url = os.getenv("STREAMLIT_SERVER_BASE_URL", "").strip()
    if base_url:
        for uri in uris:
            if uri.rstrip("/") == base_url.rstrip("/"):
                return uri

    public_url = os.getenv("STREAMLIT_PUBLIC_URL", "").strip()
    if public_url:
        for uri in uris:
            if uri.rstrip("/") == public_url.rstrip("/"):
                return uri

    if len(uris) == 1:
        return uris[0]

    # Fallback to the first URI if no exact match is found.
    return uris[0]


def get_redirect_uri():
    return _selected_redirect_uri()


def _google_client_config():
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")

    return {
        "web": {
            "client_id": client_id,
            "project_id": "cosai-prod",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": _redirect_uris(),
        }
    }


def build_google_auth_url(redirect_uri=None):
    Flow = _load_google_oauth_deps()
    state = secrets.token_urlsafe(24)
    # PKCE verifier must be reused in callback token exchange.
    code_verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    if redirect_uri is None:
        redirect_uri = _selected_redirect_uri()
    flow = Flow.from_client_config(
        _google_client_config(),
        scopes=GOOGLE_OAUTH_SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return auth_url, state, code_verifier


def complete_google_oauth(code, state, redirect_uri=None, code_verifier=None):
    Flow = _load_google_oauth_deps()
    if redirect_uri is None:
        redirect_uri = _selected_redirect_uri()
    flow = Flow.from_client_config(
        _google_client_config(),
        scopes=GOOGLE_OAUTH_SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri
    kwargs = {"code": code}
    if code_verifier:
        kwargs["code_verifier"] = code_verifier
    flow.fetch_token(**kwargs)
    creds = flow.credentials

    account_email = ""
    try:
        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=creds)
        info = service.userinfo().get().execute()
        account_email = info.get("email", "")
    except Exception:
        account_email = ""

    return {
        "account_email": account_email,
        "scopes": list(creds.scopes or []),
        "access_token": creds.token or "",
        "refresh_token": creds.refresh_token or "",
        "token_expiry": creds.expiry.isoformat() if creds.expiry else "",
    }


def check_account_health(user_id, account_id):
    account = get_active_account(user_id, account_id)
    if not account:
        return False, "Account not active."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Google dependencies. Install: pip install google-auth google-api-python-client"
        ) from exc

    try:
        scopes = (account.get("scopes") or "").split() or ["https://www.googleapis.com/auth/gmail.readonly"]
        creds = Credentials(
            token=account.get("access_token", ""),
            refresh_token=account.get("refresh_token", ""),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            scopes=scopes,
        )

        service = build("gmail", "v1", credentials=creds)
        service.users().getProfile(userId="me").execute()

        if creds.token and creds.token != account.get("access_token", ""):
            update_account_tokens(
                user_id=user_id,
                account_id=account_id,
                access_token=creds.token,
                refresh_token=creds.refresh_token or account.get("refresh_token", ""),
                token_expiry=creds.expiry.isoformat() if creds.expiry else account.get("token_expiry", ""),
            )
        update_account_health(user_id, account_id, status="healthy", error_msg="")
        return True, "Healthy"
    except Exception as exc:
        update_account_health(user_id, account_id, status="error", error_msg=str(exc))
        return False, str(exc)
