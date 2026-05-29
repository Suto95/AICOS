import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from cosai_app.auth import render_user_badge, require_login, current_user
from cosai_app.onboarding import render_account_setup

st.set_page_config(page_title="Account Setup", layout="wide")

if require_login():
    render_user_badge()
    render_account_setup(current_user())
