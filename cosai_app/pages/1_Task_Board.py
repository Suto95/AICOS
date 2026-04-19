import streamlit as st
from cosai_app.ui import render_task_board

st.set_page_config(page_title="Task Board", layout="wide")
render_task_board()
