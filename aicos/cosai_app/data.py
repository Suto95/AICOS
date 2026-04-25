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


def load_prefs(user_id=None):
    if user_id is None:
        return _load_prefs_file()

    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT prefs_json FROM user_prefs WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["prefs_json"])
    except (TypeError, json.JSONDecodeError):
        return {}


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
        try:
            entry = json.loads(r["entry_json"])
            if isinstance(entry, dict):
                memory.append(entry)
        except (TypeError, json.JSONDecodeError):
            continue
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
        try:
            event = json.loads(r["event_json"])
        except (TypeError, json.JSONDecodeError):
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
        try:
            event = json.loads(r["event_json"])
        except (TypeError, json.JSONDecodeError):
            continue
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
        try:
            event = json.loads(r["event_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        event["_user_id"] = int(r["user_id"])
        events.append(event)
    return events


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
