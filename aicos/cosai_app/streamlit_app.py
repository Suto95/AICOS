import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from cosai_app.auth import current_user, render_user_badge, require_login
from cosai_app.state import init_state

# Initialize analytics (only in production)
try:
    import streamlit_analytics
    ga_id = st.secrets.get("GOOGLE_ANALYTICS_ID")
    if ga_id:
        streamlit_analytics.start_tracking(ga_id)
except ImportError:
    pass  # Analytics not installed

st.set_page_config(page_title="AICOS", layout="wide")

if require_login():
    user = current_user()
    try:
        init_state(user_id=user["id"])
    except TypeError:
        # Backward-compat fallback if a stale state module is loaded.
        init_state()
    render_user_badge()

    st.title("AICOS")
    st.caption("Multipage app. Use the left sidebar to navigate.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Pages")
        st.markdown("- `Account Setup`: connect and configure email accounts")
        st.markdown("- `Task Board`: primary table-first workflow")
        st.markdown("- `System Insights`: memory, events, and state diagnostics")
    with c2:
        st.markdown("### Session")
        st.metric("Tasks in session", len(st.session_state.results))
        st.metric("Memory entries", len(st.session_state.memory))

    st.info("Start with `Account Setup`, then open `Task Board` to fetch and prioritize tasks.")
