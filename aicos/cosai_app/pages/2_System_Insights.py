import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st
from cosai_app.auth import current_user, developer_emails, render_user_badge, require_login
from cosai_app.insights import render_insights_page

st.set_page_config(page_title="System Insights", layout="wide")
if require_login():
    user = current_user()
    if not user or (user.get("email") or "").strip().lower() not in developer_emails():
        st.warning("System Insights is reserved for the developer.")
        try:
            st.switch_page("pages/0_Task_Board.py")
        except Exception:
            st.stop()
        st.stop()

    render_user_badge()
    render_insights_page(current_user())
