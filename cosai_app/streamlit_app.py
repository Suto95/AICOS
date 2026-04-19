import streamlit as st

from cosai_app.state import init_state

st.set_page_config(page_title="CosAI", layout="wide")
init_state()

st.title("CosAI")
st.caption("Multipage app. Use the left sidebar to navigate.")

c1, c2 = st.columns(2)
with c1:
    st.markdown("### Pages")
    st.markdown("- `Task Board`: primary table-first workflow")
    st.markdown("- `System Insights`: memory, events, and state diagnostics")
with c2:
    st.markdown("### Session")
    st.metric("Tasks in session", len(st.session_state.results))
    st.metric("Memory entries", len(st.session_state.memory))

st.info("Open `Task Board` from the sidebar to start fetching and prioritizing tasks.")
