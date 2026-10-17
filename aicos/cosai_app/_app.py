import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from cosai_app.auth import current_user, is_developer_user, require_login
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

# Hide navigation until user logs in
if not current_user():
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] { display: none; }
            [data-testid="stSidebarNavItems"] { display: none; }
            section[data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

require_login()

if current_user():
    user_email = (current_user() or {}).get("email", "").strip().lower()
    if not is_developer_user(user_email):
        st.markdown(
            """
            <style>
                a[href*="2_System_Insights"], a[href*="System_Insights"], a[href*="System%20Insights"] { display: none !important; }
                [data-testid="stSidebarNav"] a[href*="2_System_Insights"] { display: none !important; }
                [data-testid="stSidebarNav"] a[href*="System_Insights"] { display: none !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )
    st.info("👋 Welcome to AICOS! Click **Task Board** in the sidebar to get started.")
