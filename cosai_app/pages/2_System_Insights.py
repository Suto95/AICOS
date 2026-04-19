import streamlit as st
from cosai_app.insights import render_insights_page

st.set_page_config(page_title="System Insights", layout="wide")
render_insights_page()
