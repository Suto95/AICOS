import os

import streamlit as st

from .accounts import (
    build_google_auth_url,
    cache_oauth_verifier,
    check_account_health,
    complete_google_oauth,
    disconnect_account,
    ensure_login_email_account,
    list_connected_accounts,
    pop_oauth_verifier,
    upsert_google_account,
)
from .data import migrate_local_data_to_user


def render_account_setup(user):
    st.title("Account Setup")
    st.caption("Connect and manage email accounts for task ingestion.")
    ensure_login_email_account(user["id"], user.get("email", ""))

    redirect_uri = os.getenv("COSAI_REDIRECT_URI", "").strip()
    missing_oauth_env = not redirect_uri

    qp = st.query_params
    code = qp.get("code") or st.session_state.get("pending_oauth_code")
    returned_state = qp.get("state") or st.session_state.get("pending_oauth_state")
    expected_state = st.session_state.get("oauth_state")
    code_verifier = st.session_state.get("oauth_code_verifier")

    if code and returned_state:
        if expected_state and returned_state != expected_state:
            st.error("OAuth state mismatch. Please click Continue with Google again.")
        else:
            try:
                code_verifier = st.session_state.get("oauth_code_verifier")
                if not code_verifier:
                    code_verifier = pop_oauth_verifier(user["id"], returned_state)
                
                if not code_verifier:
                    st.error("OAuth verifier missing. Please click 'Add Gmail account' again.")
                    return
                
                # If Streamlit session resets after redirect, expected_state may be missing.
                # We still complete using returned state to avoid auth loops.
                token_payload = complete_google_oauth(
                    code=code,
                    state=returned_state,
                    redirect_uri=redirect_uri,
                    code_verifier=code_verifier,
                )
                upsert_google_account(user["id"], token_payload)
                st.success("Gmail account connected.")
                st.session_state.pop("oauth_state", None)
                st.session_state.pop("oauth_code_verifier", None)
                st.session_state.pop("pending_oauth_code", None)
                st.session_state.pop("pending_oauth_state", None)
                st.query_params.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Google OAuth failed: {exc}")

    accounts = list_connected_accounts(user["id"])
    has_accounts = len(accounts) > 0
    button_text = "Add another Gmail account" if has_accounts else "Add Gmail account"

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Connect Gmail")
        if not missing_oauth_env:
            try:
                auth_url, state, code_verifier = build_google_auth_url(redirect_uri=redirect_uri)
                st.session_state.oauth_state = state
                st.session_state.oauth_code_verifier = code_verifier
                cache_oauth_verifier(user["id"], state, code_verifier)
                st.link_button(button_text, auth_url, use_container_width=True)
            except Exception as exc:
                st.error(f"Unable to initialize Google OAuth: {exc}")
        else:
            st.button(button_text, use_container_width=True, disabled=True)
            st.warning("Gmail connect is not configured yet.")
            st.code(
                "Add this in .env and restart app:\n"
                "COSAI_REDIRECT_URI=https://<your-app-domain>/\n"
                "GOOGLE_OAUTH_CLIENT_ID=<client-id>\n"
                "GOOGLE_OAUTH_CLIENT_SECRET=<client-secret>",
                language="bash",
            )
    with c2:
        st.info(
            "AICOS can only read your emails and basic profile info to prioritize tasks. "
            "It cannot send, delete, or modify your emails."
        )

    st.subheader("Connected Accounts")
    if st.button("Migrate Local Data Into My Account", use_container_width=False):
        try:
            report = migrate_local_data_to_user(user["id"])
            st.success(
                f"Migrated prefs:{report['prefs']} memory:{report['memory']} events:{report['events']}."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Migration failed: {exc}")

    if not accounts:
        st.caption("No email accounts connected yet.")
        return

    for acct in accounts:
        with st.container(border=True):
            st.markdown(f"**{acct.get('account_email') or 'Unknown Gmail account'}**")
            st.caption(
                f"Provider: {acct.get('provider', 'gmail')} | Status: {acct.get('status', 'active')} | "
                f"Health: {acct.get('health_status', 'unknown')}"
            )
            if acct.get("health_error"):
                st.caption(f"Last health error: {acct.get('health_error')}")
            if acct.get("last_fetched_at"):
                st.caption(f"Last fetched: {acct.get('last_fetched_at')}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Health Check", key=f"health_{acct['id']}", use_container_width=True):
                    ok, msg = check_account_health(user["id"], acct["id"])
                    if ok:
                        st.success("Account is healthy.")
                    else:
                        st.error(f"Health check failed: {msg}")
                    st.rerun()
            with c2:
                if st.button("Disconnect", key=f"disconnect_{acct['id']}", use_container_width=True):
                    disconnect_account(user["id"], acct["id"])
                    st.success("Account disconnected.")
                    st.rerun()
