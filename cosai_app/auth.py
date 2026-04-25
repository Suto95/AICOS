import os
from datetime import datetime

import streamlit as st

from .accounts import (
    build_google_auth_url,
    cache_oauth_verifier,
    complete_google_oauth,
    ensure_login_email_account,
    pop_oauth_verifier,
    upsert_google_account,
)
from .db import get_conn, init_db


def _allowed_emails():
    raw = os.getenv("COSAI_ALLOWED_EMAILS", "")
    if not raw.strip():
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _find_or_create_user(email):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            return {"id": int(row["id"]), "email": row["email"]}

        cur = conn.execute("INSERT INTO users(email, created_at) VALUES(?, ?)", (email, now))
        conn.commit()
        return {"id": int(cur.lastrowid), "email": email}


def current_user():
    return st.session_state.get("user")


def require_login():
    init_db()
    # Preserve OAuth callback params if user lands here before being logged in.
    qp = st.query_params
    if qp.get("code"):
        st.session_state.pending_oauth_code = qp.get("code")
    if qp.get("state"):
        st.session_state.pending_oauth_state = qp.get("state")

    if current_user():
        return True

    redirect_uri = os.getenv("COSAI_REDIRECT_URI", "").strip()
    code = st.session_state.get("pending_oauth_code")
    returned_state = st.session_state.get("pending_oauth_state")
    expected_state = st.session_state.get("oauth_state")
    code_verifier = st.session_state.get("oauth_code_verifier")

    if code and returned_state and redirect_uri:
        if expected_state and returned_state != expected_state:
            st.error("OAuth state mismatch. Please try Continue with Google again.")
        else:
            try:
                if not code_verifier:
                    code_verifier = pop_oauth_verifier(user_id=0, state=returned_state)
                token_payload = complete_google_oauth(
                    code=code,
                    state=returned_state,
                    redirect_uri=redirect_uri,
                    code_verifier=code_verifier,
                )
                email = (token_payload.get("account_email") or "").strip().lower()
                if "@" not in email:
                    st.error("Google did not return an email. Please retry.")
                else:
                    allowlist = _allowed_emails()
                    if allowlist and email not in allowlist:
                        st.error("This email is not enabled for the current rollout.")
                    else:
                        user = _find_or_create_user(email)
                        st.session_state.user = user
                        ensure_login_email_account(user["id"], email)
                        upsert_google_account(user["id"], token_payload)
                        st.session_state.pop("oauth_state", None)
                        st.session_state.pop("oauth_code_verifier", None)
                        st.session_state.pop("pending_oauth_code", None)
                        st.session_state.pop("pending_oauth_state", None)
                        st.query_params.clear()
                        st.rerun()
            except Exception as exc:
                st.error(f"Google sign-in failed: {exc}")

    st.title("AICOS Login")
    st.caption("Start with Google to sign in and connect Gmail in one step.")

    if redirect_uri:
        try:
            auth_url, state, code_verifier = build_google_auth_url(redirect_uri=redirect_uri)
            st.session_state.oauth_state = state
            st.session_state.oauth_code_verifier = code_verifier
            # user_id=0 means pre-login cache bucket.
            cache_oauth_verifier(user_id=0, state=state, code_verifier=code_verifier)
            st.link_button("Continue with Google", auth_url, use_container_width=True)
        except Exception as exc:
            st.error(f"Unable to start Google sign-in: {exc}")
    else:
        st.button("Continue with Google", use_container_width=True, disabled=True)
        st.warning("Set COSAI_REDIRECT_URI to enable Google sign-in.")

    st.markdown("or sign in with email")
    email = st.text_input("Email")

    if st.button("Continue", use_container_width=True):
        normalized = email.strip().lower()
        if "@" not in normalized:
            st.error("Enter a valid email.")
            return False

        allowlist = _allowed_emails()
        if allowlist and normalized not in allowlist:
            st.error("This email is not enabled for the current rollout.")
            return False

        st.session_state.user = _find_or_create_user(normalized)
        st.rerun()

    return False


def render_user_badge():
    user = current_user()
    if not user:
        return

    with st.sidebar:
        st.caption(f"Signed in: {user['email']}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("user", None)
            st.session_state.pop("active_user_id", None)
            st.session_state.pop("oauth_state", None)
            st.session_state.pop("oauth_code_verifier", None)
            st.session_state.pop("pending_oauth_code", None)
            st.session_state.pop("pending_oauth_state", None)
            st.rerun()
