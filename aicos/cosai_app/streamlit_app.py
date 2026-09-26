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

st.set_page_config(page_title="AICOS", page_icon="⚡", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1400px;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        }
        .stMetric {
            background: rgba(17, 24, 39, 0.75);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 16px;
            padding: 0.75rem 1rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 2rem;
            font-weight: 700;
        }
        div[data-testid="stVerticalBlock"] > div {
            border-radius: 18px;
        }
        .app-hero {
            background: linear-gradient(135deg, rgba(99,102,241,0.18), rgba(16,185,129,0.08));
            border: 1px solid rgba(148,163,184,0.16);
            border-radius: 22px;
            padding: 1.4rem 1.5rem;
            margin-bottom: 1rem;
        }
        .section-card {
            background: rgba(15, 23, 42, 0.70);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 18px;
            padding: 1.2rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

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
                    <div style="font-size:0.8rem; letter-spacing:0.12em; text-transform:uppercase; color:#A5B4FC; font-weight:700;">AI Task OS</div>
                    <h1 style="margin:0.25rem 0; color:#F8FAFC;">AICOS</h1>
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
        with st.container(border=True):
            st.markdown("### Workspace")
            st.markdown("- **Task Board**: intake, prioritize, and resolve email-derived work")
            st.markdown("- **Account Setup**: connect Gmail and manage account health")
            st.markdown("- **System Insights**: memory, events, and learning diagnostics")
    with c2:
        with st.container(border=True):
            st.markdown("### Quick start")
            st.info("Start with Account Setup, then open Task Board to fetch and prioritize your inbox.")
            st.button("Open Task Board", key="home_open_board", use_container_width=True)
            if st.session_state.get("home_open_board"):
                st.switch_page("pages/0_Task_Board.py")

    st.markdown("<br>", unsafe_allow_html=True)
