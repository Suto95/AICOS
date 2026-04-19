from datetime import datetime

import pandas as pd
import streamlit as st

from gmail_ingest import fetch_emails
from .config import BUCKET_ORDER
from .data import append_event, append_memory_entry
from .logic import (
    analyze_messages,
    detect_done_suggestions,
    generate_reasoning,
    score_task,
    select_questions,
)
from .state import init_state, push_undo_snapshot, undo_last_action


def get_result_by_id(results, task_id):
    for row in results:
        if row["id"] == task_id:
            return row
    return None


def render_task_board():
    init_state()

    st.title("CosAI Prioritizer")
    st.caption("Table-first workflow: prioritize, reassign, add signals, reason, done, and delete.")

    top_a, top_b, top_c, top_d, top_e = st.columns([2, 1.2, 1.2, 0.8, 0.8])
    with top_a:
        max_results = st.number_input("Emails to fetch", min_value=1, max_value=100, value=10, step=1)
    with top_b:
        done_suggest_threshold = st.slider("Done confidence", 0.2, 0.9, 0.4, 0.05)
    with top_c:
        if st.button("Fetch + Analyze", use_container_width=True):
            try:
                with st.spinner("Fetching emails from Gmail..."):
                    messages = fetch_emails(int(max_results))
                    st.session_state.latest_messages = messages
                with st.spinner("Analyzing tasks with LLM..."):
                    st.session_state.results = analyze_messages(messages, st.session_state.prefs, st.session_state.memory)
                    st.session_state.done_suggestions = detect_done_suggestions(
                        st.session_state.results,
                        messages,
                        suggest_threshold=done_suggest_threshold,
                    )
                st.success(f"Loaded {len(st.session_state.results)} task(s).")
            except Exception as e:
                st.error(f"Fetch/analyze failed: {e}")
    with top_d:
        if st.button("+", use_container_width=True, help="Add new task"):
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
        st.info("No tasks loaded yet. Click `Fetch + Analyze` above.")
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
                    append_event("task_created_manual", next_id, new_task_text.strip(), {"bucket": new_bucket})
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
            append_event("bucket_changed", target["id"], target["task"], {"to_bucket": new_bucket})
            bucket_or_order_changed = True

        new_order = int(edited["order"])
        if new_order != int(target.get("manual_rank", target["id"])):
            if not bucket_or_order_changed:
                push_undo_snapshot()
            target["manual_rank"] = new_order
            target["updated_at"] = datetime.now().isoformat()
            append_event("order_changed", target["id"], target["task"], {"new_order": new_order})
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
                append_event("reason_generated", target["id"], target["task"], {})
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
                            append_event("task_deleted", target["id"], target["task"], {})
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
                                entry = append_memory_entry(target["task"], target["meta"], "clarification")
                                if entry:
                                    st.session_state.memory.append(entry)
                                append_event("clarifications_applied", target["id"], target["task"], {"fields": questions})
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
                        append_event("task_reopened", r["id"], r["task"], {"bucket": r.get("bucket")})
                        st.success(f"Task {r['id']} reopened.")
                        st.rerun()
