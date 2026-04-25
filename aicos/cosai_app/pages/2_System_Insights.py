import streamlit as st
from cosai_app.auth import current_user, render_user_badge, require_login
from cosai_app.insights import render_insights_page

st.set_page_config(page_title="System Insights", layout="wide")
if require_login():
    render_user_badge()
    render_insights_page(current_user())
