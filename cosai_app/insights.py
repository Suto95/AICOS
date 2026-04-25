import pandas as pd
import streamlit as st

from .data import load_events
from .state import init_state


def render_insights_page(user):
    try:
        init_state(user_id=user["id"])
    except TypeError:
        init_state()

    st.title("System Insights")
    st.caption("Operational view of state, learning memory, and events.")

    prefs = st.session_state.prefs
    memory = st.session_state.memory
    results = st.session_state.results
    events = load_events(limit=300, user_id=user["id"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Tasks", len([r for r in results if r.get("status", "open") == "open"]))
    c2.metric("Done Tasks", len([r for r in results if r.get("status") == "done"]))
    c3.metric("Memory Entries", len(memory))
    c4.metric("Recent Events", len(events))

    st.subheader("Preferences")
    st.caption("AICOS learns what you treat as high-impact and uses it to personalize future task prioritization.")
    if prefs:
        pref_rows = []
        for signal, counts in prefs.items():
            if not isinstance(counts, dict):
                continue
            pref_rows.append(
                {
                    "Signal": signal.replace("_", " ").title(),
                    "Low": int(counts.get("low", 0)),
                    "Medium": int(counts.get("medium", 0)),
                    "High": int(counts.get("high", 0)),
                    "Yes": int(counts.get("yes", 0)),
                    "No": int(counts.get("no", 0)),
                }
            )
        if pref_rows:
            pref_df = pd.DataFrame(pref_rows)
            pref_df["Total"] = pref_df[["Low", "Medium", "High", "Yes", "No"]].sum(axis=1)
            st.dataframe(pref_df, hide_index=True, use_container_width=True)
        else:
            st.info("No learned preference signals yet.")
    else:
        st.info("No learned preference signals yet.")

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
