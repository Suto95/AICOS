import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from cosai_app.auth import require_login
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

require_login()
st.info("👋 Welcome to AICOS! Click **Task Board** in the sidebar to get started.")
