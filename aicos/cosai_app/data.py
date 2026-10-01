import json
import os
from datetime import datetime

from .config import PREF_FILE, MEMORY_FILE, EVENT_FILE, LEARNABLE_FIELDS, SIGNAL_FIELDS
from .db import get_conn, init_db


def _load_prefs_file():
    if not os.path.exists(PREF_FILE):
        return {}
    try:
        with open(PREF_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_prefs_file(prefs):
    with open(PREF_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


def _decode_json_payload(value, fallback):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def load_prefs(user_id=None):
    if user_id is None:
        return _load_prefs_file()

    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT prefs_json FROM user_prefs WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {}
    payload = _decode_json_payload(row["prefs_json"], {})
    return payload if isinstance(payload, dict) else {}


def save_prefs(prefs, user_id=None):
    if user_id is None:
        _save_prefs_file(prefs)
        return

    init_db()
    now = datetime.now().isoformat()
    payload = json.dumps(prefs)
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM user_prefs WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE user_prefs SET prefs_json = ?, updated_at = ? WHERE user_id = ?",
                (payload, now, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO user_prefs(user_id, prefs_json, updated_at) VALUES (?, ?, ?)",
                (user_id, payload, now),
            )
        conn.commit()


def update_preferences(task, prefs):
    for field in LEARNABLE_FIELDS:
        val = task.get(field)
        if not val:
            continue
        prefs.setdefault(field, {"low": 0, "medium": 0, "high": 0})
        if val in prefs[field]:
            prefs[field][val] += 1
    return prefs


def get_learned_weight(field, prefs):
    if field not in prefs:
        return 1.0
    values = prefs[field]
    total = sum(values.values())
    if total == 0:
        return 1.0
    return 1 + (values.get("high", 0) / total)


def _load_memory_file():
    if not os.path.exists(MEMORY_FILE):
        return []

    memory = []
    try:
        with open(MEMORY_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        memory.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return memory


def load_memory(user_id=None):
    if user_id is None:
        return _load_memory_file()

    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT entry_json
            FROM task_memory
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()
    memory = []
    for r in rows:
        entry = _decode_json_payload(r["entry_json"], {})
        if isinstance(entry, dict):
            memory.append(entry)
    return memory


def append_memory_entry(task_text, task_meta, source, user_id=None):
    signals = {}
    for field in SIGNAL_FIELDS:
        val = task_meta.get(field)
        if val:
            signals[field] = val

    if len(signals) < 2:
        return None

    lead_days = None
    if signals.get("deadline"):
        try:
            d = datetime.strptime(signals["deadline"], "%Y-%m-%d").date()
            lead_days = (d - datetime.now().date()).days
            if lead_days < 0:
                lead_days = 0
        except ValueError:
            lead_days = None

    entry = {
        "timestamp": datetime.now().isoformat(),
        "task_text": task_text,
        "sender": task_meta.get("sender", ""),
        "signals": signals,
        "source": source,
        "deadline_lead_days": lead_days,
    }

    if user_id is None:
        with open(MEMORY_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    init_db()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_memory(user_id, entry_json, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, json.dumps(entry), entry["timestamp"]),
        )
        conn.commit()
    return entry


def append_event(event_type, task_id, task_text, payload=None, user_id=None):
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "task_id": task_id,
        "task_text": task_text,
        "payload": payload or {},
    }
    if user_id is None:
        try:
            with open(EVENT_FILE, "a") as f:
                f.write(json.dumps(event) + "\n")
        except OSError:
            return None
        return event

    init_db()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_events(user_id, event_json, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, json.dumps(event), event["timestamp"]),
        )
        conn.commit()
    return event


def _load_events_file(limit=None):
    if not os.path.exists(EVENT_FILE):
        return []
    events = []
    try:
        with open(EVENT_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(event)
    except OSError:
        return []
    if limit is None:
        return events
    return events[-limit:]


def load_task_event_history(task_id, limit=8, user_id=None):
    if user_id is None:
        events = _load_events_file()
        history = [e for e in events if e.get("task_id") == task_id]
        return history[-limit:]

    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT event_json
            FROM task_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 600
            """,
            (user_id,),
        ).fetchall()

    history = []
    for r in reversed(rows):
        event = _decode_json_payload(r["event_json"], {})
        if not isinstance(event, dict):
            continue
        if event.get("task_id") == task_id:
            history.append(event)
    return history[-limit:]


def load_events(limit=200, user_id=None):
    if user_id is None:
        return _load_events_file(limit=limit)

    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT event_json
            FROM task_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    events = []
    for r in reversed(rows):
        event = _decode_json_payload(r["event_json"], {})
        if isinstance(event, dict):
            events.append(event)
    return events


def load_events_all_users(limit=2000, exclude_user_id=None):
    init_db()
    query = """
        SELECT user_id, event_json
        FROM task_events
        ORDER BY id DESC
        LIMIT ?
    """
    params = [limit]
    if exclude_user_id is not None:
        query = """
            SELECT user_id, event_json
            FROM task_events
            WHERE user_id != ?
            ORDER BY id DESC
            LIMIT ?
        """
        params = [exclude_user_id, limit]

    with get_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    events = []
    for r in reversed(rows):
        event = _decode_json_payload(r["event_json"], {})
        if not isinstance(event, dict):
            continue
        event["_user_id"] = int(r["user_id"])
        events.append(event)
    return events


def _normalize_task_snapshot(snapshot, event):
    payload = event.get("payload") or {}
    timestamp = event.get("timestamp") or datetime.now().isoformat()
    task_id = event.get("task_id")
    task_text = event.get("task_text") or ""

    if isinstance(snapshot, dict):
        task = snapshot.copy()
        task.setdefault("id", task_id)
        task.setdefault("task", task_text)
        task.setdefault("score", 0)
        task.setdefault("bucket", payload.get("bucket") or "REVIEW LATER")
        task.setdefault("predicted_bucket", task.get("bucket", "REVIEW LATER"))
        task.setdefault("reason", [])
        task.setdefault("meta", {"task": task.get("task", task_text)})
        task.setdefault("inferred", {})
        task.setdefault("status", "open")
        task.setdefault("manual_override", False)
        task.setdefault("override_comment", "")
        task.setdefault("source", payload.get("source", ""))
        task.setdefault("created_at", timestamp)
        task.setdefault("updated_at", timestamp)
        if task.get("manual_rank") is None:
            task.pop("manual_rank", None)
        return task

    if task_id is None or not task_text:
        return None

    bucket = payload.get("bucket") or "REVIEW LATER"
    source = payload.get("source") or ("manual" if event.get("event_type") == "task_created_manual" else "email")
    return {
        "id": task_id,
        "task": task_text,
        "score": 0,
        "bucket": bucket,
        "predicted_bucket": bucket,
        "reason": [],
        "meta": {"task": task_text},
        "inferred": {},
        "status": "open",
        "manual_override": source == "manual",
        "override_comment": "",
        "source": source,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def load_persisted_tasks(user_id=None, limit=5000):
    events = load_events(limit=limit, user_id=user_id)
    tasks = {}

    for event in events:
        event_type = event.get("event_type")
        task_id = event.get("task_id")
        payload = event.get("payload") or {}
        snapshot = _normalize_task_snapshot(payload.get("task_snapshot"), event)

        if event_type in ("task_created_manual", "task_imported_email"):
            if snapshot is not None:
                tasks[snapshot["id"]] = snapshot
            continue

        if event_type == "task_edited":
            if snapshot is not None:
                tasks[snapshot["id"]] = {**tasks.get(snapshot["id"], {}), **snapshot}
            elif task_id is not None:
                task = tasks.get(task_id)
                if task is not None:
                    updated_text = payload.get("new_task") or payload.get("task_snapshot", {}).get("task") or task.get("task")
                    task["task"] = updated_text
                    task.setdefault("meta", {})["task"] = updated_text
                    task["updated_at"] = event.get("timestamp") or task.get("updated_at")
            continue

        if task_id is None:
            continue

        if snapshot is not None:
            tasks[task_id] = {**tasks.get(task_id, {}), **snapshot}
            continue

        task = tasks.get(task_id)
        if task is None:
            continue

        if event_type == "bucket_changed":
            task["bucket"] = payload.get("to_bucket", task.get("bucket"))
            task["manual_override"] = task.get("bucket") != task.get("predicted_bucket", task.get("bucket"))
        elif event_type == "order_changed":
            task["manual_rank"] = payload.get("new_order", task.get("manual_rank", task.get("id")))
        elif event_type == "task_marked_done":
            task["status"] = "done"
        elif event_type == "task_deleted":
            task["status"] = "deleted"
        elif event_type == "task_reopened":
            task["status"] = "open"
            task["bucket"] = payload.get("bucket", task.get("bucket"))

        task["updated_at"] = event.get("timestamp") or task.get("updated_at")

    return sorted(tasks.values(), key=lambda row: row.get("id", 0))


def migrate_local_data_to_user(user_id):
    """
    One-time migration utility for legacy single-user JSON/JSONL files.
    Returns dict with migrated counts.
    """
    init_db()
    report = {"prefs": 0, "memory": 0, "events": 0}

    prefs = _load_prefs_file()
    if prefs:
        save_prefs(prefs, user_id=user_id)
        report["prefs"] = 1

    local_memory = _load_memory_file()
    if local_memory:
        with get_conn() as conn:
            existing = conn.execute("SELECT COUNT(1) AS c FROM task_memory WHERE user_id = ?", (user_id,)).fetchone()
            if int(existing["c"]) == 0:
                for entry in local_memory:
                    ts = entry.get("timestamp") or datetime.now().isoformat()
                    conn.execute(
                        """
                        INSERT INTO task_memory(user_id, entry_json, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (user_id, json.dumps(entry), ts),
                    )
                conn.commit()
                report["memory"] = len(local_memory)

    local_events = _load_events_file()
    if local_events:
        with get_conn() as conn:
            existing = conn.execute("SELECT COUNT(1) AS c FROM task_events WHERE user_id = ?", (user_id,)).fetchone()
            if int(existing["c"]) == 0:
                for event in local_events:
                    ts = event.get("timestamp") or datetime.now().isoformat()
                    conn.execute(
                        """
                        INSERT INTO task_events(user_id, event_json, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (user_id, json.dumps(event), ts),
                    )
                conn.commit()
                report["events"] = len(local_events)

    return report
