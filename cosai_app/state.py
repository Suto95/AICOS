import copy
import streamlit as st

from .data import load_prefs, load_memory


def init_state(user_id=None):
    active = st.session_state.get("active_user_id")
    user_switched = user_id is not None and active != user_id

    if user_switched:
        st.session_state.active_user_id = user_id
        st.session_state.prefs = load_prefs(user_id=user_id)
        st.session_state.memory = load_memory(user_id=user_id)
        st.session_state.results = []
        st.session_state.latest_messages = []
        st.session_state.done_suggestions = []
        st.session_state.undo_stack = []
        st.session_state.show_add_task = False
        st.session_state.pending_delete_ids = []
        st.session_state.signal_wizard_task_id = None
        st.session_state.signal_wizard_step = 0
        st.session_state.selected_account_id = None
        return

    if "prefs" not in st.session_state:
        st.session_state.prefs = load_prefs(user_id=user_id)
    if "results" not in st.session_state:
        st.session_state.results = []
    if "memory" not in st.session_state:
        st.session_state.memory = load_memory(user_id=user_id)
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
    if "selected_account_id" not in st.session_state:
        st.session_state.selected_account_id = None


def push_undo_snapshot():
    st.session_state.undo_stack.append(copy.deepcopy(st.session_state.results))
    if len(st.session_state.undo_stack) > 30:
        st.session_state.undo_stack = st.session_state.undo_stack[-30:]


def undo_last_action():
    if st.session_state.undo_stack:
        st.session_state.results = st.session_state.undo_stack.pop()
        return True
    return False
