from datetime import datetime, timedelta
import re

import streamlit as st

from . import gmail_ingest
from .theme import apply_theme
from .accounts import (
    DEFAULT_GMAIL_QUERY_FILTER,
    get_active_account,
    list_connected_accounts,
    update_account_fetch_success,
    update_account_health,
    update_account_tokens,
)
from .config import BUCKET_ORDER
from .data import append_event, load_events, load_events_all_users
from .logic import (
    analyze_messages,
    derive_user_hint_profile,
    is_near_duplicate_task,
    merge_hint_profiles,
    score_task,
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


def _is_duplicate_import(existing_task, new_task):
    existing_meta = existing_task.get("meta", {})
    new_meta = new_task.get("meta", {})
    existing_thread = existing_meta.get("thread_id", "")
    new_thread = new_meta.get("thread_id", "")
    same_thread = bool(existing_thread and new_thread and existing_thread == new_thread)
    return same_thread or is_near_duplicate_task(existing_task, new_task)


def task_snapshot(task):
    snapshot = {
        "id": task.get("id"),
        "task": task.get("task", ""),
        "score": task.get("score", 0),
        "bucket": task.get("bucket", ""),
        "predicted_bucket": task.get("predicted_bucket", task.get("bucket", "")),
        "reason": task.get("reason", []),
        "meta": task.get("meta", {}),
        "inferred": task.get("inferred", {}),
        "status": task.get("status", "open"),
        "manual_override": task.get("manual_override", False),
        "override_comment": task.get("override_comment", ""),
        "source": task.get("source", ""),
        "created_at": task.get("created_at", ""),
        "updated_at": task.get("updated_at", ""),
    }
    if task.get("manual_rank") is not None:
        snapshot["manual_rank"] = task.get("manual_rank")
    return snapshot


def task_event_payload(task, extra=None):
    payload = dict(extra or {})
    payload["task_snapshot"] = task_snapshot(task)
    return payload


def merge_new_results(existing_results, new_results):
    merged = list(existing_results or [])
    next_id = max((r.get("id", -1) for r in merged), default=-1) + 1
    added_count = 0
    added_results = []

    for result in new_results or []:
        if any(_is_duplicate_import(existing, result) for existing in merged):
            continue
        result = result.copy()
        result["id"] = next_id
        next_id += 1
        added_count += 1
        added_results.append(result)
        merged.append(result)

    return merged, added_count, added_results


def render_task_board(user):
    apply_theme()
    try:
        init_state(user_id=user["id"])
    except TypeError:
        init_state()

    st.markdown(
        """
        <div class="task-board-header">
            <div style="font-size:0.8rem; letter-spacing:0.12em; text-transform:uppercase; color:#A5B4FC; font-weight:700;">Priority workspace</div>
            <h1 style="margin:0.25rem 0; color:#F8FAFC;">AICOS Prioritizer</h1>
            <div class="task-board-subtitle">Turn Gmail signals into clear, actionable work.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    accounts = list_connected_accounts(user["id"])
    has_account_setup = bool(accounts)
    connected_accounts = [a for a in accounts if a.get("status") == "active"]
    account_options = {f"{a.get('account_email') or 'Gmail'} (id {a['id']})": a["id"] for a in connected_accounts}
    labels = list(account_options.keys())
    default_idx = 0
    selected = st.session_state.get("selected_account_id")
    if selected is not None and selected in account_options.values():
        for i, label in enumerate(labels):
            if account_options[label] == selected:
                default_idx = i
                break

    open_tasks = sum(1 for r in st.session_state.results if r.get("status", "open") == "open")
    high_priority = sum(1 for r in st.session_state.results if r.get("status", "open") == "open" and float(r.get("score", 0) or 0) >= 0.75)
    recent_memory = len(st.session_state.memory)

    st.markdown(
        f"""
        <div class="task-board-kpi-grid">
            <div style="background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.18); border-radius:18px; padding:0.9rem 1rem;">
                <div style="color:#A5B4FC; font-size:0.7rem; letter-spacing:0.12em; text-transform:uppercase; font-weight:700;">Open tasks</div>
                <div style="font-size:2rem; font-weight:700; margin-top:0.35rem; color:#F8FAFC;">{open_tasks}</div>
            </div>
            <div style="background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.18); border-radius:18px; padding:0.9rem 1rem;">
                <div style="color:#A5B4FC; font-size:0.7rem; letter-spacing:0.12em; text-transform:uppercase; font-weight:700;">High priority</div>
                <div style="font-size:2rem; font-weight:700; margin-top:0.35rem; color:#F8FAFC;">{high_priority}</div>
            </div>
            <div style="background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.18); border-radius:18px; padding:0.9rem 1rem;">
                <div style="color:#A5B4FC; font-size:0.7rem; letter-spacing:0.12em; text-transform:uppercase; font-weight:700;">Memory</div>
                <div style="font-size:2rem; font-weight:700; margin-top:0.35rem; color:#F8FAFC;">{recent_memory}</div>
            </div>
            <div style="background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.18); border-radius:18px; padding:0.9rem 1rem;">
                <div style="color:#A5B4FC; font-size:0.7rem; letter-spacing:0.12em; text-transform:uppercase; font-weight:700;">Accounts</div>
                <div style="font-size:2rem; font-weight:700; margin-top:0.35rem; color:#F8FAFC;">{len(connected_accounts)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_a, top_b, top_c, top_d, top_e = st.columns([2.2, 1.8, 1.2, 0.9, 0.9])
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
                    new_results = analyze_messages(
                        messages,
                        st.session_state.prefs,
                        st.session_state.memory,
                        hint_profile=hint_profile,
                    )
                    st.session_state.results, added_count, added_results = merge_new_results(
                        st.session_state.results,
                        new_results,
                    )
                    for result in added_results:
                        append_event(
                            "task_imported_email",
                            result["id"],
                            result["task"],
                            task_event_payload(
                                result,
                                {
                                    "account_id": st.session_state.get("selected_account_id"),
                                    "source": "email",
                                    "sender": result.get("meta", {}).get("sender", ""),
                                    "sender_domain": _sender_domain(result.get("meta", {}).get("sender", "")),
                                },
                            ),
                            user_id=user["id"],
                        )
                st.success(
                    f"Added {added_count} new task(s) from {duration_label.lower()}. "
                    f"Total tasks: {len(st.session_state.results)}."
                )
            except Exception as e:
                account_id = st.session_state.get("selected_account_id")
                if account_id is not None:
                    update_account_health(user["id"], int(account_id), status="error", error_msg=str(e))
                st.error(f"Fetch/analyze failed: {e}")
    with top_d:
        if st.button("➕ Add task", use_container_width=True, help="Add new task"):
            st.session_state.show_add_task = not st.session_state.show_add_task
    with top_e:
        if st.button("↶", use_container_width=True, help="Undo last action"):
            if undo_last_action():
                st.success("Undid last action.")
                st.rerun()
            else:
                st.info("Nothing to undo.")

    results = st.session_state.results
    if not results:
        st.info("No tasks loaded yet. Click `Fetch + Analyze` above or add a manual task with the + button.")
        if not has_account_setup:
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
                    new_task = {
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
                    st.session_state.results.append(new_task)
                    append_event(
                        "task_created_manual",
                        next_id,
                        new_task_text.strip(),
                        task_event_payload(
                            new_task,
                            {
                                "bucket": new_bucket,
                                "account_id": st.session_state.get("selected_account_id"),
                                "source": "manual",
                            },
                        ),
                        user_id=user["id"],
                    )
                    st.success("Task added.")
                    st.session_state.show_add_task = False
                    st.rerun()

    visible_results = [r for r in results if r.get("status", "open") == "open"]
    visible_results = sorted(
        visible_results,
        key=lambda r: (r.get("manual_rank") if r.get("manual_rank") is not None else r["id"], -r.get("score", 0)),
    )

    st.markdown(
        """
        <div style="background:linear-gradient(135deg, rgba(99,102,241,0.12), rgba(14,165,233,0.08)); border:1px solid rgba(148,163,184,0.18); border-radius:18px; padding:0.9rem 1rem; margin:1.1rem 0 0.6rem;">
            <div style="font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; color:#A5B4FC; font-weight:700;">Priority queue</div>
            <div style="color:#F8FAFC; font-size:1.2rem; font-weight:700; margin-top:0.2rem;">Prioritized Tasks</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("Review tasks by bucket, then move, rank, complete, or delete them from each task card.")

    if not visible_results:
        st.info("No open tasks to show.")

    id_to_row = {r["id"]: r for r in results}

    tasks_by_bucket = {bucket: [] for bucket in BUCKET_ORDER if bucket != "ERROR"}
    for task in visible_results:
        bucket = task.get("bucket")
        if bucket not in tasks_by_bucket:
            bucket = "REVIEW LATER"
        tasks_by_bucket[bucket].append(task)

    for bucket in tasks_by_bucket:
        tasks_by_bucket[bucket] = sorted(
            tasks_by_bucket[bucket],
            key=lambda r: (r.get("manual_rank") if r.get("manual_rank") is not None else r["id"], -r.get("score", 0)),
        )

    bucket_rows = [
        ("DO NOW", "SCHEDULE", "DELEGATE"),
        ("REVIEW LATER", "ELIMINATE"),
    ]

    for bucket_row in bucket_rows:
        columns = st.columns(len(bucket_row))
        for col, bucket in zip(columns, bucket_row):
            bucket_tasks = tasks_by_bucket.get(bucket, [])
            with col:
                st.markdown(
                    f"""
                    <div class="bucket-section-header">
                        <div>{bucket}</div>
                        <span>{len(bucket_tasks)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if not bucket_tasks:
                    st.caption("No open tasks.")
                    continue

                for idx, task in enumerate(bucket_tasks):
                    task_id = task["id"]
                    with st.container(border=True):
                        st.markdown(f'<div class="task-card-title">{task["task"]}</div>', unsafe_allow_html=True)
                        if task.get("source") == "manual":
                            st.markdown('<div class="task-card-meta"><span>manual</span></div>', unsafe_allow_html=True)

                        with st.expander("Move/order"):
                            bucket_options = [b for b in BUCKET_ORDER if b != "ERROR"]
                            current_bucket = task.get("bucket") if task.get("bucket") in bucket_options else bucket
                            selected_bucket = st.selectbox(
                                "Bucket",
                                options=bucket_options,
                                index=bucket_options.index(current_bucket),
                                key=f"task_bucket_{task_id}",
                            )
                            if selected_bucket != task.get("bucket"):
                                push_undo_snapshot()
                                task["bucket"] = selected_bucket
                                task["manual_override"] = selected_bucket != task.get("predicted_bucket", selected_bucket)
                                task["updated_at"] = datetime.now().isoformat()
                                append_event(
                                    "bucket_changed",
                                    task["id"],
                                    task["task"],
                                    task_event_payload(task, {"to_bucket": selected_bucket}),
                                    user_id=user["id"],
                                )
                                st.toast(f"Moved task {task_id} to {selected_bucket}.")
                                st.rerun()

                            saved_rank = task.get("manual_rank")
                            rank_value = int(saved_rank if saved_rank is not None else idx)
                            new_rank = st.number_input(
                                "Order",
                                min_value=0,
                                step=1,
                                value=rank_value,
                                key=f"task_order_{task_id}",
                            )
                            if int(new_rank) != rank_value:
                                push_undo_snapshot()
                                task["manual_rank"] = int(new_rank)
                                task["updated_at"] = datetime.now().isoformat()
                                append_event(
                                    "order_changed",
                                    task["id"],
                                    task["task"],
                                    task_event_payload(task, {"new_order": int(new_rank)}),
                                    user_id=user["id"],
                                )
                                st.toast(f"Updated order for task {task_id}.")
                                st.rerun()

                        done_col, delete_col = st.columns(2)
                        with done_col:
                            if st.button("✓", key=f"task_done_{task_id}", use_container_width=True, help="Mark done"):
                                push_undo_snapshot()
                                task["status"] = "done"
                                task["updated_at"] = datetime.now().isoformat()
                                append_event(
                                    "task_marked_done",
                                    task["id"],
                                    task["task"],
                                    task_event_payload(
                                        task,
                                        {
                                            "via_card_cta": True,
                                        },
                                    ),
                                    user_id=user["id"],
                                )
                                st.success(f"Marked task {task_id} done.")
                                st.rerun()
                        with delete_col:
                            if st.button("🗑", key=f"task_delete_{task_id}", use_container_width=True, help="Delete task"):
                                st.session_state.pending_delete_ids = [task_id]
                                st.rerun()

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
                                task_event_payload(
                                    target,
                                    {
                                        "account_id": st.session_state.get("selected_account_id"),
                                        "source": target.get("source", ""),
                                        "sender": target.get("meta", {}).get("sender", ""),
                                        "sender_domain": _sender_domain(target.get("meta", {}).get("sender", "")),
                                    },
                                ),
                                user_id=user["id"],
                            )
                    st.session_state.pending_delete_ids = []
                    st.success("Task(s) deleted.")
                    st.rerun()
            with c2:
                if st.button("Cancel Delete", use_container_width=True):
                    st.session_state.pending_delete_ids = []
                    st.rerun()

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
                        append_event(
                            "task_reopened",
                            r["id"],
                            r["task"],
                            task_event_payload(r, {"bucket": r.get("bucket")}),
                            user_id=user["id"],
                        )
                        st.success(f"Task {r['id']} reopened.")
                        st.rerun()
