import streamlit as st
from cosai_app.auth import current_user, render_user_badge, require_login
from cosai_app.ui import render_task_board

st.set_page_config(page_title="Task Board", layout="wide")
if require_login():
    render_user_badge()
    render_task_board(current_user())
