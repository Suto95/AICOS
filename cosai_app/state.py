import copy
import streamlit as st

from .data import load_prefs, load_memory


def init_state():
    if "prefs" not in st.session_state:
        st.session_state.prefs = load_prefs()
    if "results" not in st.session_state:
        st.session_state.results = []
    if "memory" not in st.session_state:
        st.session_state.memory = load_memory()
    if "latest_messages" not in st.session_state:
        st.session_state.latest_messages = []
    if "done_suggestions" not in st.session_state:
        st.session_state.done_suggestions = []
    if "undo_stack" not in st.session_state:
        st.session_state.undo_stack = []
    if "show_add_task" not in st.session_state:
        st.session_state.show_add_task = False
    if "pending_delete_ids" not in st.session_state:
        st.session_state.pending_delete_ids = []
    if "signal_wizard_task_id" not in st.session_state:
        st.session_state.signal_wizard_task_id = None
    if "signal_wizard_step" not in st.session_state:
        st.session_state.signal_wizard_step = 0


def push_undo_snapshot():
    st.session_state.undo_stack.append(copy.deepcopy(st.session_state.results))
    if len(st.session_state.undo_stack) > 30:
        st.session_state.undo_stack = st.session_state.undo_stack[-30:]


def undo_last_action():
    if st.session_state.undo_stack:
        st.session_state.results = st.session_state.undo_stack.pop()
        return True
    return False
