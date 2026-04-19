import pandas as pd
import streamlit as st

from .data import load_events
from .state import init_state


def render_insights_page():
    init_state()

    st.title("System Insights")
    st.caption("Operational view of state, learning memory, and events.")

    prefs = st.session_state.prefs
    memory = st.session_state.memory
    results = st.session_state.results
    events = load_events(limit=300)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Tasks", len([r for r in results if r.get("status", "open") == "open"]))
    c2.metric("Done Tasks", len([r for r in results if r.get("status") == "done"]))
    c3.metric("Memory Entries", len(memory))
    c4.metric("Recent Events", len(events))

    st.subheader("Preferences")
    st.json(prefs)

    st.subheader("Recent Memory")
    if memory:
        st.dataframe(pd.DataFrame(memory[-30:]), hide_index=True, use_container_width=True)
    else:
        st.info("No memory entries yet.")

    st.subheader("Recent Events")
    if events:
        st.dataframe(pd.DataFrame(events[-100:]), hide_index=True, use_container_width=True)
    else:
        st.info("No events yet.")
