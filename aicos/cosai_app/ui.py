from datetime import datetime, timedelta
import re

import pandas as pd
import streamlit as st

from . import gmail_ingest
from .accounts import (
    DEFAULT_GMAIL_QUERY_FILTER,
    get_active_account,
    list_connected_accounts,
    update_account_fetch_success,
    update_account_health,
    update_account_tokens,
)
from .config import BUCKET_ORDER
from .data import append_event, append_memory_entry, load_events, load_events_all_users
from .logic import (
    analyze_messages,
    derive_user_hint_profile,
    detect_done_suggestions,
    generate_reasoning,
    merge_hint_profiles,
    score_task,
    select_questions,
)
from .state import init_state, push_undo_snapshot, undo_last_action

FETCH_LIMIT = 200
DURATION_OPTIONS = {
    "Last 3 hours": timedelta(hours=3),
    "Last 24 hours": timedelta(hours=24),
    "Last 3 days": timedelta(days=3),
    "Last 7 days": timedelta(days=7),
}


def get_result_by_id(results, task_id):
    for row in results:
        if row["id"] == task_id:
            return row
    return None


def _filter_messages_by_duration(messages, window):
    now = datetime.now().astimezone()
    cutoff = now - window
    filtered = []
    for msg in messages:
        raw_ts = msg.get("timestamp", "")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=now.tzinfo)
        if ts >= cutoff:
            filtered.append(msg)
    return filtered


def _sender_domain(sender):
    raw = (sender or "").strip().lower()
    match = re.search(r"([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", raw)
    email = match.group(1) if match else raw
    if "@" not in email:
        return ""
    return email.split("@", 1)[1]


def render_task_board(user):
    try:
        init_state(user_id=user["id"])
    except TypeError:
        init_state()

    st.title("AICOS Prioritizer")

    connected_accounts = [a for a in list_connected_accounts(user["id"]) if a.get("status") == "active"]
    account_options = {f"{a.get('account_email') or 'Gmail'} (id {a['id']})": a["id"] for a in connected_accounts}
    labels = list(account_options.keys())
    default_idx = 0
    selected = st.session_state.get("selected_account_id")
    if selected is not None and selected in account_options.values():
        for i, label in enumerate(labels):
            if account_options[label] == selected:
                default_idx = i
                break

    top_a, top_b, top_c, top_d, top_e, top_f = st.columns([2, 1.7, 1.2, 1.2, 0.8, 0.8])
    with top_a:
        if connected_accounts:
            selected_label = st.selectbox("Email account", options=labels, index=default_idx)
            st.session_state.selected_account_id = account_options[selected_label]
        else:
            selected_label = None
            st.info("No active email account connected. Open Account Setup to connect Gmail.")
    with top_b:
        duration_label = st.selectbox("Fetch window", options=list(DURATION_OPTIONS.keys()), index=1)
    with top_c:
        done_suggest_threshold = st.slider("Done confidence", 0.2, 0.9, 0.6, 0.05)
    with top_d:
        if st.button("Fetch + Analyze", use_container_width=True, disabled=not connected_accounts):
            try:
                with st.spinner("Fetching emails from Gmail..."):
                    account = get_active_account(user["id"], st.session_state.selected_account_id)
                    if not account:
                        st.error("Selected account is not active. Reconnect from Account Setup.")
                        st.stop()
                    fetch_connected = getattr(gmail_ingest, "fetch_emails_for_account", None)
                    if fetch_connected is not None:
                        messages, refreshed = fetch_connected(
                            account=account,
                            max_results=FETCH_LIMIT,
                            query=DEFAULT_GMAIL_QUERY_FILTER,
                        )
                    else:
                        # Backward-compat path if an old gmail_ingest module is loaded.
                        legacy_fetch = getattr(gmail_ingest, "fetch_emails", None)
                        if legacy_fetch is None:
                            raise RuntimeError(
                                "gmail_ingest does not expose fetch_emails_for_account or fetch_emails. Restart Streamlit."
                            )
                        messages = legacy_fetch(FETCH_LIMIT)
                        refreshed = account
                    messages = _filter_messages_by_duration(messages, DURATION_OPTIONS[duration_label])
                    update_account_tokens(
                        user_id=user["id"],
                        account_id=account["id"],
                        access_token=refreshed.get("access_token", account.get("access_token", "")),
                        refresh_token=refreshed.get("refresh_token", account.get("refresh_token", "")),
                        token_expiry=refreshed.get("token_expiry", account.get("token_expiry", "")),
                    )
                    update_account_fetch_success(user["id"], account["id"])
                    st.session_state.latest_messages = messages
                with st.spinner("Analyzing tasks with LLM..."):
                    user_events = load_events(limit=1000, user_id=user["id"])
                    global_events = load_events_all_users(limit=5000, exclude_user_id=user["id"])
                    user_hint_profile = derive_user_hint_profile(
                        user_events,
                        account_id=st.session_state.selected_account_id,
                    )
                    global_hint_profile = derive_user_hint_profile(
                        global_events,
                        account_id=st.session_state.selected_account_id,
                        min_action_count=5,
                        min_noise_count=5,
                        min_noise_domain_count=8,
                    )
                    hint_profile = merge_hint_profiles(user_hint_profile, global_hint_profile)
                    st.session_state.results = analyze_messages(
                        messages,
                        st.session_state.prefs,
                        st.session_state.memory,
                        hint_profile=hint_profile,
                    )
                    st.session_state.done_suggestions = detect_done_suggestions(
                        st.session_state.results,
                        messages,
                        suggest_threshold=done_suggest_threshold,
                        user_id=user["id"],
                    )
                st.success(f"Loaded {len(st.session_state.results)} task(s) from {duration_label.lower()}.")
            except Exception as e:
                account_id = st.session_state.get("selected_account_id")
                if account_id is not None:
                    update_account_health(user["id"], int(account_id), status="error", error_msg=str(e))
                st.error(f"Fetch/analyze failed: {e}")
    with top_e:
        if st.button("➕ Add task", use_container_width=True, help="Add new task"):
            st.session_state.show_add_task = not st.session_state.show_add_task
    with top_f:
        if st.button("↶", use_container_width=True, help="Undo last action"):
            if undo_last_action():
                st.success("Undid last action.")
                st.rerun()
            else:
                st.info("Nothing to undo.")

    results = st.session_state.results
    if not results:
        st.info("No tasks loaded yet. Click `Fetch + Analyze` above or add a manual task with the + button.")
        st.markdown("If you're new, start with Account Setup.")
        if st.button("Open Account Setup", use_container_width=True, key="open_account_setup"):
            st.experimental_set_query_params(page="Account Setup")
            st.experimental_rerun()

    if not connected_accounts:
        st.markdown("---")
        st.info("No active email account connected. Add Gmail in Account Setup or add tasks manually.")
        st.markdown("---")
        if not results:
            return

    if st.session_state.show_add_task:
        with st.container(border=True):
            st.markdown("**Add New Task**")
            c1, c2 = st.columns([4, 2])
            new_task_text = c1.text_input("Task", key="new_task_text")
            new_bucket = c2.selectbox("Bucket", [b for b in BUCKET_ORDER if b != "ERROR"], key="new_task_bucket")
            if st.button("Submit New Task", key="submit_new_task"):
                if not new_task_text.strip():
                    st.warning("Task text is required.")
                else:
                    push_undo_snapshot()
                    next_id = max((r["id"] for r in results), default=-1) + 1
                    task_meta = {"task": new_task_text.strip()}
                    score, predicted_bucket, reason = score_task(task_meta, st.session_state.prefs)
                    st.session_state.results.append(
                        {
                            "id": next_id,
                            "task": new_task_text.strip(),
                            "score": score,
                            "bucket": new_bucket,
                            "predicted_bucket": predicted_bucket,
                            "reason": reason,
                            "meta": task_meta,
                            "inferred": {},
                            "status": "open",
                            "manual_override": True,
                            "override_comment": "",
                            "source": "manual",
                            "created_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat(),
                        }
                    )
                    append_event(
                        "task_created_manual",
                        next_id,
                        new_task_text.strip(),
                        {
                            "bucket": new_bucket,
                            "account_id": st.session_state.get("selected_account_id"),
                            "source": "manual",
                        },
                        user_id=user["id"],
                    )
                    st.success("Task added.")
                    st.session_state.show_add_task = False
                    st.rerun()

    done_suggestion_by_task = {}
    for s in st.session_state.done_suggestions:
        task_id = s.get("task_id")
        if task_id is None:
            continue
        existing = done_suggestion_by_task.get(task_id)
        if not existing or s.get("llm_confidence", 0) > existing.get("llm_confidence", 0):
            done_suggestion_by_task[task_id] = s

    visible_results = [r for r in results if r.get("status", "open") == "open"]
    visible_results = sorted(visible_results, key=lambda r: (r.get("manual_rank", r["id"]), -r.get("score", 0)))

    table_rows = []
    for idx, r in enumerate(visible_results):
        hint = "💡 done?" if r["id"] in done_suggestion_by_task else ""
        table_rows.append(
            {
                "id": r["id"],
                "task": r["task"],
                "bucket": r["bucket"],
                "order": int(r.get("manual_rank", idx)),
                "done?": hint,
                "Add signals": False,
                "Reason?": False,
                "Reason": "; ".join(r.get("reason", [])) if r.get("reason") else "",
                "✓": False,
                "🗑": False,
            }
        )

    st.subheader("Prioritized Tasks")
    editor_df = st.data_editor(
        pd.DataFrame(table_rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
            "task": st.column_config.TextColumn("task", disabled=True, width="large"),
            "bucket": st.column_config.SelectboxColumn("bucket", options=[b for b in BUCKET_ORDER if b != "ERROR"], required=True),
            "order": st.column_config.NumberColumn("order", min_value=0, step=1, help="Manual reorder rank."),
            "done?": st.column_config.TextColumn("done?", disabled=True, help="Potential done suggestion available."),
            "Add signals": st.column_config.CheckboxColumn("Add signals"),
            "Reason?": st.column_config.CheckboxColumn("Reason?"),
            "Reason": st.column_config.TextColumn("Reason", disabled=True, width="large"),
            "✓": st.column_config.CheckboxColumn("✓"),
            "🗑": st.column_config.CheckboxColumn("🗑"),
        },
        key="task_table_editor",
    )

    if editor_df.empty:
        st.info("No open tasks to show.")
        return

    id_to_row = {r["id"]: r for r in results}
    bucket_or_order_changed = False
    done_ids, reason_ids, delete_ids, signal_ids = [], [], [], []

    for _, edited in editor_df.iterrows():
        task_id = int(edited["id"])
        target = id_to_row.get(task_id)
        if not target:
            continue

        new_bucket = str(edited["bucket"])
        if new_bucket != target.get("bucket"):
            if not bucket_or_order_changed:
                push_undo_snapshot()
            target["bucket"] = new_bucket
            target["manual_override"] = new_bucket != target.get("predicted_bucket", new_bucket)
            target["updated_at"] = datetime.now().isoformat()
            append_event("bucket_changed", target["id"], target["task"], {"to_bucket": new_bucket}, user_id=user["id"])
            bucket_or_order_changed = True

        new_order = int(edited["order"])
        if new_order != int(target.get("manual_rank", target["id"])):
            if not bucket_or_order_changed:
                push_undo_snapshot()
            target["manual_rank"] = new_order
            target["updated_at"] = datetime.now().isoformat()
            append_event("order_changed", target["id"], target["task"], {"new_order": new_order}, user_id=user["id"])
            bucket_or_order_changed = True

        if bool(edited["✓"]):
            done_ids.append(task_id)
        if bool(edited["Reason?"]):
            reason_ids.append(task_id)
        if bool(edited["🗑"]):
            delete_ids.append(task_id)
        if bool(edited["Add signals"]):
            signal_ids.append(task_id)

    if bucket_or_order_changed:
        st.toast("Table updates applied.")
        st.rerun()

    if done_ids:
        push_undo_snapshot()
        for task_id in done_ids:
            target = id_to_row.get(task_id)
            if not target:
                continue
            target["status"] = "done"
            target["updated_at"] = datetime.now().isoformat()
            suggestion = done_suggestion_by_task.get(task_id, {})
            append_event(
                "task_marked_done",
                target["id"],
                target["task"],
                {
                    "via_table_cta": True,
                    "reason": suggestion.get("reason", ""),
                    "evidence": suggestion.get("evidence", ""),
                },
                user_id=user["id"],
            )
        st.success(f"Marked {len(done_ids)} task(s) done.")
        st.rerun()

    if reason_ids:
        push_undo_snapshot()
        for task_id in reason_ids:
            target = id_to_row.get(task_id)
            if not target:
                continue
            try:
                target["reason"] = [generate_reasoning(target["task"])]
                target["updated_at"] = datetime.now().isoformat()
                append_event("reason_generated", target["id"], target["task"], {}, user_id=user["id"])
            except Exception:
                continue
        st.success(f"Generated reason for {len(reason_ids)} task(s).")
        st.rerun()

    if delete_ids:
        st.session_state.pending_delete_ids = delete_ids

    if st.session_state.pending_delete_ids:
        with st.container(border=True):
            st.warning(f"Delete {len(st.session_state.pending_delete_ids)} task(s)?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirm Delete", use_container_width=True):
                    push_undo_snapshot()
                    delete_set = set(st.session_state.pending_delete_ids)
                    for task_id in delete_set:
                        target = id_to_row.get(task_id)
                        if target:
                            target["status"] = "deleted"
                            target["updated_at"] = datetime.now().isoformat()
                            append_event(
                                "task_deleted",
                                target["id"],
                                target["task"],
                                {
                                    "account_id": st.session_state.get("selected_account_id"),
                                    "source": target.get("source", ""),
                                    "sender": target.get("meta", {}).get("sender", ""),
                                    "sender_domain": _sender_domain(target.get("meta", {}).get("sender", "")),
                                },
                                user_id=user["id"],
                            )
                    st.session_state.pending_delete_ids = []
                    st.success("Task(s) deleted.")
                    st.rerun()
            with c2:
                if st.button("Cancel Delete", use_container_width=True):
                    st.session_state.pending_delete_ids = []
                    st.rerun()

    if signal_ids and st.session_state.signal_wizard_task_id is None:
        st.session_state.signal_wizard_task_id = signal_ids[0]
        st.session_state.signal_wizard_step = 0
        st.rerun()

    wizard_task_id = st.session_state.signal_wizard_task_id
    if wizard_task_id is not None:
        target = id_to_row.get(wizard_task_id)
        if not target:
            st.session_state.signal_wizard_task_id = None
            st.session_state.signal_wizard_step = 0
        else:
            questions = select_questions(target["meta"])
            with st.container(border=True):
                st.markdown(f"**Add signals: Task {target['id']} - {target['task']}**")
                if not questions:
                    st.success("No missing critical signals.")
                    st.session_state.signal_wizard_task_id = None
                    st.session_state.signal_wizard_step = 0
                else:
                    step = min(st.session_state.signal_wizard_step, len(questions) - 1)
                    field = questions[step]
                    st.caption(f"Step {step + 1}/{len(questions)}")
                    key = f"wizard_{target['id']}_{field}"

                    if field == "deadline":
                        current_deadline = target["meta"].get("deadline")
                        if current_deadline:
                            try:
                                default_date = datetime.strptime(current_deadline, "%Y-%m-%d").date()
                            except ValueError:
                                default_date = datetime.now().date()
                        else:
                            default_date = datetime.now().date()
                        value = st.date_input("deadline", value=default_date, key=key).strftime("%Y-%m-%d")
                    elif field in ("penalty_for_delay", "blocks_others"):
                        options = ["", "yes", "no"]
                        current = target["meta"].get(field) or ""
                        value = st.selectbox(field, options=options, index=options.index(current) if current in options else 0, key=key)
                    else:
                        options = ["", "low", "medium", "high"]
                        current = target["meta"].get(field) or ""
                        value = st.selectbox(field, options=options, index=options.index(current) if current in options else 0, key=key)

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("Save & Next", key=f"wizard_next_{target['id']}"):
                            if value:
                                target["meta"][field] = value
                            st.session_state.signal_wizard_step += 1
                            if st.session_state.signal_wizard_step >= len(questions):
                                push_undo_snapshot()
                                score, predicted_bucket, reason = score_task(target["meta"], st.session_state.prefs)
                                target["score"] = score
                                target["predicted_bucket"] = predicted_bucket
                                target["reason"] = reason if reason else []
                                if not target.get("manual_override"):
                                    target["bucket"] = predicted_bucket
                                try:
                                    auto_reason = generate_reasoning(target["task"])
                                    target["reason"] = [auto_reason]
                                except Exception:
                                    pass
                                target["updated_at"] = datetime.now().isoformat()
                                entry = append_memory_entry(target["task"], target["meta"], "clarification", user_id=user["id"])
                                if entry:
                                    st.session_state.memory.append(entry)
                                append_event("clarifications_applied", target["id"], target["task"], {"fields": questions}, user_id=user["id"])
                                st.session_state.signal_wizard_task_id = None
                                st.session_state.signal_wizard_step = 0
                                st.success("Signals updated, rescored, and reason generated.")
                                st.rerun()
                            else:
                                st.rerun()
                    with c2:
                        if st.button("Skip", key=f"wizard_skip_{target['id']}"):
                            st.session_state.signal_wizard_step += 1
                            if st.session_state.signal_wizard_step >= len(questions):
                                st.session_state.signal_wizard_task_id = None
                                st.session_state.signal_wizard_step = 0
                            st.rerun()
                    with c3:
                        if st.button("Close", key=f"wizard_close_{target['id']}"):
                            st.session_state.signal_wizard_task_id = None
                            st.session_state.signal_wizard_step = 0
                            st.rerun()

    with st.expander("Done suggestion details"):
        if not done_suggestion_by_task:
            st.caption("No active done suggestions.")
        else:
            for task_id, s in done_suggestion_by_task.items():
                st.markdown(f"- **Task {task_id}** | confidence `{s.get('llm_confidence', 0)}` | {s.get('reason', '')}")
                if s.get("evidence"):
                    st.caption(f"Evidence: {s['evidence']}")

    done_rows = [r for r in results if r.get("status") == "done"]
    with st.expander("Reopen done tasks"):
        if not done_rows:
            st.caption("No done tasks.")
        else:
            for r in done_rows:
                c1, c2 = st.columns([6, 1])
                with c1:
                    st.write(f"Task {r['id']}: {r['task']}")
                with c2:
                    if st.button("Reopen", key=f"reopen_done_{r['id']}"):
                        push_undo_snapshot()
                        r["status"] = "open"
                        r["updated_at"] = datetime.now().isoformat()
                        append_event("task_reopened", r["id"], r["task"], {"bucket": r.get("bucket")}, user_id=user["id"])
                        st.success(f"Task {r['id']} reopened.")
                        st.rerun()
