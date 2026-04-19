import json
import os
from datetime import datetime

from .config import PREF_FILE, MEMORY_FILE, EVENT_FILE, LEARNABLE_FIELDS, SIGNAL_FIELDS


def load_prefs():
    if not os.path.exists(PREF_FILE):
        return {}
    try:
        with open(PREF_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_prefs(prefs):
    with open(PREF_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


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


def load_memory():
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


def append_memory_entry(task_text, task_meta, source):
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

    with open(MEMORY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def append_event(event_type, task_id, task_text, payload=None):
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "task_id": task_id,
        "task_text": task_text,
        "payload": payload or {},
    }
    try:
        with open(EVENT_FILE, "a") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        return None
    return event


def load_task_event_history(task_id, limit=8):
    if not os.path.exists(EVENT_FILE):
        return []
    history = []
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
                if event.get("task_id") == task_id:
                    history.append(event)
    except OSError:
        return []
    return history[-limit:]


def load_events(limit=200):
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
    return events[-limit:]
