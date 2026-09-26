import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from cosai_app.auth import current_user, render_user_badge, require_login
from cosai_app.state import init_state
from cosai_app.theme import apply_theme

# Initialize analytics (only in production)
try:
    import streamlit_analytics
    ga_id = st.secrets.get("GOOGLE_ANALYTICS_ID")
    if ga_id:
        streamlit_analytics.start_tracking(ga_id)
except ImportError:
    pass  # Analytics not installed

st.set_page_config(page_title="AICOS", page_icon="⚡", layout="wide")
apply_theme()

if require_login():
    user = current_user()
    try:
        init_state(user_id=user["id"])
    except TypeError:
        # Backward-compat fallback if a stale state module is loaded.
        init_state()
    render_user_badge()

    st.markdown(
        """
        <div class="app-hero">
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; flex-wrap:wrap;">
                <div>
                    <div class="eyebrow">AI Task OS</div>
                    <h1 style="margin:0.3rem 0 0; color:#F8FAFC; font-size:2.4rem; line-height:1.1;">AICOS</h1>
                </div>
                <div style="color:#CBD5E1; font-size:0.95rem;">Multipage workflow · email-aware prioritization</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    with metric_col_1:
        st.metric("Tasks in session", len(st.session_state.results))
    with metric_col_2:
        st.metric("Memory entries", len(st.session_state.memory))
    with metric_col_3:
        st.metric("Accounts", len([a for a in getattr(st.session_state, "connected_accounts", []) if a.get("status") == "active"]))

    c1, c2 = st.columns(2)
    with c1:
        with st.container():
            st.markdown('<div class="workspace-card">', unsafe_allow_html=True)
            st.markdown("### Workspace")
            st.markdown("- **Task Board**: intake, prioritize, and resolve email-derived work")
            st.markdown("- **Account Setup**: connect Gmail and manage account health")
            st.markdown("- **System Insights**: memory, events, and learning diagnostics")
            st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        with st.container():
            st.markdown('<div class="feature-card">', unsafe_allow_html=True)
            st.markdown("### Quick start")
            st.info("Start with Account Setup, then open Task Board to fetch and prioritize your inbox.")
            st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
            st.button("Open Task Board", key="home_open_board", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            if st.session_state.get("home_open_board"):
                st.switch_page("pages/0_Task_Board.py")
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
