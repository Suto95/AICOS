import json
import re
from datetime import datetime, timedelta

from .config import (
    SIGNAL_FIELDS,
    IMPACT_WEIGHTS,
    IMPORTANCE_MAP,
    FIELD_CHOICES,
    INFER_THRESHOLDS,
    client,
)
from .data import get_learned_weight, load_task_event_history


# ---------- generic utils ----------
def safe_json_parse(content):
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None


def normalize_task(task):
    if not isinstance(task, dict):
        return {}

    normalized = task.copy()
    for key in SIGNAL_FIELDS:
        value = normalized.get(key)
        if isinstance(value, str):
            value = value.strip().lower()
            normalized[key] = value or None
    return normalized


def parse_task_id_set(raw):
    ids = set()
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            ids.add(int(token))
    return ids


def tokenize_text(text):
    raw_tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    normalized = set()
    for t in raw_tokens:
        if len(t) > 5 and t.endswith("ing"):
            t = t[:-3]
        elif len(t) > 4 and t.endswith("ed"):
            t = t[:-2]
        elif len(t) > 4 and t.endswith("es"):
            t = t[:-2]
        elif len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        normalized.add(t)
    return normalized


def text_similarity(a, b):
    a_tokens = tokenize_text(a)
    b_tokens = tokenize_text(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def get_message_text_for_done(message):
    parts = [
        message.get("subject", ""),
        message.get("snippet", ""),
        message.get("body", ""),
        message.get("text", ""),
    ]
    return "\n".join([p for p in parts if p]).strip()


def message_dedupe_key(message):
    message_id = (message.get("message_id") or "").strip()
    if message_id:
        return f"mid:{message_id}"

    thread_id = (message.get("thread_id") or "").strip()
    sender = (message.get("sender") or "").strip().lower()
    subject = (message.get("subject") or message.get("text") or "").strip().lower()
    text_sig = " ".join(sorted(tokenize_text(get_message_text_for_done(message))))[:180]
    return f"fallback:{thread_id}|{sender}|{subject}|{text_sig}"


# ---------- inference layer ----------
def find_missing_signals(task):
    return [f for f in SIGNAL_FIELDS if task.get(f) is None]


def normalize_distribution(scores):
    total = sum(scores.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in scores.items()}


def recency_weight(ts):
    try:
        created = datetime.fromisoformat(ts).date()
    except (TypeError, ValueError):
        return 1.0
    age_days = max(0, (datetime.now().date() - created).days)
    return 1 / (1 + age_days / 30)


def global_prior_distribution(field, prefs, memory):
    choices = FIELD_CHOICES.get(field, ())
    if not choices:
        return {}

    if field in prefs:
        counts = prefs[field]
        dist = {c: float(counts.get(c, 0)) for c in choices}
        dist = normalize_distribution(dist)
        if dist:
            return dist

    counts = {c: 0.0 for c in choices}
    for entry in memory:
        val = entry.get("signals", {}).get(field)
        if val in counts:
            counts[val] += 1
    return normalize_distribution(counts)


def predict_categorical_signal(field, task_text, sender, prefs, memory, k=5):
    choices = FIELD_CHOICES.get(field, ())
    if not choices:
        return None, 0.0, "none"

    neighbors = []
    sender_scores = {c: 0.0 for c in choices}

    for entry in memory:
        signals = entry.get("signals", {})
        val = signals.get(field)
        if val not in choices:
            continue

        sim = text_similarity(task_text, entry.get("task_text", ""))
        if sender and entry.get("sender") and sender == entry.get("sender"):
            sim += 0.15
        if sim <= 0:
            continue

        weight = sim * recency_weight(entry.get("timestamp"))
        neighbors.append((weight, val))

        if sender and entry.get("sender") and sender == entry.get("sender"):
            sender_scores[val] += 1.0 * recency_weight(entry.get("timestamp"))

    neighbors.sort(key=lambda x: x[0], reverse=True)
    top_neighbors = neighbors[:k]

    neighbor_scores = {c: 0.0 for c in choices}
    for weight, val in top_neighbors:
        neighbor_scores[val] += weight
    neighbor_scores = normalize_distribution(neighbor_scores)

    sender_scores = normalize_distribution(sender_scores)
    global_scores = global_prior_distribution(field, prefs, memory)

    blended = {c: 0.0 for c in choices}
    contributions = {c: {"similar_tasks": 0.0, "sender_prior": 0.0, "global_prior": 0.0} for c in choices}

    if neighbor_scores:
        for c in choices:
            part = 0.65 * neighbor_scores.get(c, 0.0)
            blended[c] += part
            contributions[c]["similar_tasks"] += part

    if sender_scores:
        for c in choices:
            part = 0.2 * sender_scores.get(c, 0.0)
            blended[c] += part
            contributions[c]["sender_prior"] += part

    if global_scores:
        for c in choices:
            part = 0.15 * global_scores.get(c, 0.0)
            blended[c] += part
            contributions[c]["global_prior"] += part

    blended = normalize_distribution(blended)
    if not blended:
        return None, 0.0, "none"

    prediction = max(blended, key=blended.get)
    confidence = blended[prediction]
    source = max(contributions[prediction], key=contributions[prediction].get)
    return prediction, confidence, source


def predict_deadline_signal(task_text, sender, memory, k=5):
    samples = []
    for entry in memory:
        lead_days = entry.get("deadline_lead_days")
        if lead_days is None:
            continue

        sim = text_similarity(task_text, entry.get("task_text", ""))
        if sender and entry.get("sender") and sender == entry.get("sender"):
            sim += 0.15
        if sim <= 0:
            continue

        weight = sim * recency_weight(entry.get("timestamp"))
        samples.append((weight, int(lead_days)))

    samples.sort(key=lambda x: x[0], reverse=True)
    samples = samples[:k]
    if not samples:
        return None, 0.0, "none"

    total_w = sum(w for w, _ in samples)
    if total_w <= 0:
        return None, 0.0, "none"

    weighted_lead = round(sum(w * d for w, d in samples) / total_w)
    weighted_lead = max(0, min(45, weighted_lead))
    predicted = datetime.now().date() + timedelta(days=weighted_lead)
    confidence = min(0.95, total_w / max(1, len(samples)))
    return predicted.strftime("%Y-%m-%d"), confidence, "similar_tasks"


def infer_missing_signals(task, prefs, memory):
    inferred = {}
    task_text = task.get("task", "")
    sender = task.get("sender", "")

    for field in find_missing_signals(task):
        if field == "deadline":
            pred, confidence, source = predict_deadline_signal(task_text, sender, memory)
        else:
            pred, confidence, source = predict_categorical_signal(field, task_text, sender, prefs, memory)

        if not pred:
            continue

        threshold = INFER_THRESHOLDS.get(field, 0.75)
        auto_fill = confidence >= threshold
        if auto_fill:
            task[field] = pred

        inferred[field] = {
            "value": pred,
            "confidence": round(confidence, 2),
            "source": source,
            "auto_filled": auto_fill,
        }

    return task, inferred


# ---------- scoring ----------
def extract_task(message):
    prompt = f"""
Extract structured task.

Message: "{message['text']}"

Return JSON:
- task
- deadline
- urgency_signal
- importance_signal
- penalty_for_delay
- blocks_others
- outcome_value
- strategic_alignment
- reversibility
- visibility
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    return safe_json_parse(response.choices[0].message.content)


def compute_features(task, prefs):
    today = datetime.now().date()

    if task.get("deadline"):
        try:
            d = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
            days = (d - today).days
        except ValueError:
            days = 3
    else:
        days = 5

    deadline_score = max(0.0, min(1.0, 1 / (max(days, 0) + 1)))

    penalty = 1.0 if task.get("penalty_for_delay") == "yes" else 0.3
    blocking = 1.0 if task.get("blocks_others") == "yes" else 0.3

    urgency = 0.4 * deadline_score + 0.3 * penalty + 0.3 * blocking

    outcome = IMPORTANCE_MAP.get(task.get("outcome_value"), 0.5)
    strategic = IMPORTANCE_MAP.get(task.get("strategic_alignment"), 0.5)
    visibility = IMPORTANCE_MAP.get(task.get("visibility"), 0.5)
    reversibility = IMPORTANCE_MAP.get(task.get("reversibility"), 0.5)

    outcome_w = 0.35 * get_learned_weight("outcome_value", prefs)
    strategic_w = 0.30 * get_learned_weight("strategic_alignment", prefs)

    importance = (
        outcome_w * outcome + strategic_w * strategic + 0.20 * visibility + 0.15 * (1 - reversibility)
    )

    return urgency, importance


def prioritize(urgency, importance, task):
    score = 0.5 * urgency + 0.5 * importance
    missing = find_missing_signals(task)
    uncertainty = len(missing)

    if urgency >= 0.65 and importance >= 0.65:
        bucket = "DO NOW"
    elif importance >= 0.6:
        bucket = "SCHEDULE"
    elif urgency >= 0.6:
        bucket = "DELEGATE"
    elif uncertainty >= 3:
        bucket = "REVIEW LATER"
    elif urgency < 0.3 and importance < 0.3:
        bucket = "ELIMINATE"
    else:
        bucket = "REVIEW LATER"

    return round(score, 2), bucket


def explain(task, urgency, importance):
    reasons = []
    if urgency > 0.75:
        reasons.append("Urgent deadline or dependency")
    if importance > 0.75:
        reasons.append("High impact or strategic")
    if task.get("blocks_others") == "yes":
        reasons.append("Blocks team progress")
    return reasons


def score_task(task, prefs):
    urgency, importance = compute_features(task, prefs)
    score, bucket = prioritize(urgency, importance, task)
    reasoning = explain(task, urgency, importance)
    return score, bucket, reasoning


def generate_reasoning(task):
    prompt = f"Explain why this task matters in 10 words:\n{task}"
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return res.choices[0].message.content.strip()


# ---------- question selection ----------
def simulate_score(task, override=None):
    if override is None:
        override = {}
    temp = task.copy()
    temp.update(override)
    urgency, importance = compute_features(temp, prefs={})
    score, bucket = prioritize(urgency, importance, temp)
    return score, bucket


def is_field_critical(task, field):
    extremes = {
        "deadline": ["2026-03-30", "2026-04-10"],
        "penalty_for_delay": ["yes", "no"],
        "blocks_others": ["yes", "no"],
        "outcome_value": ["high", "low"],
        "strategic_alignment": ["high", "low"],
        "visibility": ["high", "low"],
        "reversibility": ["low", "high"],
    }

    if field not in extremes:
        return False

    low_val, high_val = extremes[field]
    _, bucket_low = simulate_score(task, {field: low_val})
    _, bucket_high = simulate_score(task, {field: high_val})
    return bucket_low != bucket_high


def select_questions(task, max_q=2):
    missing = find_missing_signals(task)
    critical = [f for f in missing if is_field_critical(task, f)]

    if not critical and missing:
        critical = sorted(missing, key=lambda x: IMPACT_WEIGHTS.get(x, 0), reverse=True)[:1]

    return critical[:max_q]


# ---------- dedupe ----------
def signal_completeness(task_meta):
    return sum(1 for f in SIGNAL_FIELDS if task_meta.get(f))


def is_near_duplicate_task(task_a, task_b, sim_threshold=0.82):
    text_a = (task_a.get("task") or "").strip().lower()
    text_b = (task_b.get("task") or "").strip().lower()
    if not text_a or not text_b:
        return False
    if text_a == text_b:
        return True
    if text_a in text_b or text_b in text_a:
        return True
    return text_similarity(text_a, text_b) >= sim_threshold


def pick_better_task(existing, incoming):
    existing_meta = existing.get("meta", {})
    incoming_meta = incoming.get("meta", {})

    existing_score = float(existing.get("score", 0))
    incoming_score = float(incoming.get("score", 0))
    existing_complete = signal_completeness(existing_meta)
    incoming_complete = signal_completeness(incoming_meta)

    if incoming_complete > existing_complete:
        return incoming
    if incoming_complete < existing_complete:
        return existing
    if incoming_score > existing_score:
        return incoming
    return existing


def dedupe_results(results):
    unique = []
    for row in results:
        row_meta = row.get("meta", {})
        row_thread = row_meta.get("thread_id", "")
        duplicate_index = None

        for idx, existing in enumerate(unique):
            existing_meta = existing.get("meta", {})
            existing_thread = existing_meta.get("thread_id", "")
            same_thread = bool(row_thread and existing_thread and row_thread == existing_thread)
            same_task = is_near_duplicate_task(existing, row)
            if same_thread or same_task:
                duplicate_index = idx
                break

        if duplicate_index is None:
            unique.append(row)
        else:
            unique[duplicate_index] = pick_better_task(unique[duplicate_index], row)

    for idx, row in enumerate(unique):
        row["id"] = idx

    return unique


# ---------- done suggestions ----------
def retrieve_done_candidates(open_tasks, message, top_k=6, min_score=0.08):
    msg_text = get_message_text_for_done(message)
    msg_sender = message.get("sender", "")
    scored = []

    for task in open_tasks:
        score = text_similarity(task.get("task", ""), msg_text)
        task_sender = task.get("meta", {}).get("sender", "")
        if task_sender and msg_sender and task_sender == msg_sender:
            score += 0.15
        if score >= min_score:
            scored.append((score, task))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def llm_done_verdict(email_text, email_sender, task, event_history):
    prompt = f"""
You are verifying whether an email suggests an existing task is completed.

Task:
- id: {task.get("id")}
- title: {task.get("task")}
- current_bucket: {task.get("bucket")}
- status: {task.get("status")}

Task event history (oldest to newest):
{json.dumps(event_history, ensure_ascii=True)}

New email:
- sender: {email_sender}
- text: {email_text}

Return strict JSON:
{{
  "label": "POTENTIAL_DONE" | "NOT_DONE" | "UNSURE",
  "confidence": 0.0 to 1.0,
  "reason": "short reason",
  "evidence": "quoted phrase or summary from the email/task context"
}}

Rules:
- Be conservative. If evidence is weak, return "UNSURE".
- Never assume completion without explicit or strongly implied evidence.
"""
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    parsed = safe_json_parse(response.choices[0].message.content)
    if not isinstance(parsed, dict):
        return {"label": "UNSURE", "confidence": 0.0, "reason": "invalid_parse", "evidence": ""}

    raw_label = str(parsed.get("label", "UNSURE")).strip().upper()
    label_aliases = {
        "DONE": "POTENTIAL_DONE",
        "COMPLETED": "POTENTIAL_DONE",
        "RESOLVED": "POTENTIAL_DONE",
        "FIXED": "POTENTIAL_DONE",
        "YES": "POTENTIAL_DONE",
        "NOT_DONE": "NOT_DONE",
        "OPEN": "NOT_DONE",
        "IN_PROGRESS": "NOT_DONE",
        "NO": "NOT_DONE",
        "UNSURE": "UNSURE",
        "UNKNOWN": "UNSURE",
    }
    label = label_aliases.get(raw_label, raw_label)
    if label not in {"POTENTIAL_DONE", "NOT_DONE", "UNSURE"}:
        label = "UNSURE"

    raw_confidence = parsed.get("confidence", 0.0)
    try:
        if isinstance(raw_confidence, str) and raw_confidence.strip().endswith("%"):
            confidence = float(raw_confidence.strip().replace("%", "")) / 100.0
        else:
            confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1.0:
        confidence = confidence / 100.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "label": label,
        "confidence": confidence,
        "reason": str(parsed.get("reason", "")),
        "evidence": str(parsed.get("evidence", "")),
    }


def detect_done_suggestions(results, messages, suggest_threshold=0.4):
    open_tasks = [r for r in results if r.get("status", "open") == "open"]
    suggestions_by_task = {}
    seen_messages = set()

    for msg in messages or []:
        dedupe_key = message_dedupe_key(msg)
        if dedupe_key in seen_messages:
            continue
        seen_messages.add(dedupe_key)

        candidates = retrieve_done_candidates(open_tasks, msg, top_k=6, min_score=0.08)
        best_for_message = None

        for retrieval_score, task in candidates:
            history = load_task_event_history(task["id"], limit=8)
            msg_text = get_message_text_for_done(msg)
            verdict = llm_done_verdict(
                email_text=msg_text,
                email_sender=msg.get("sender", ""),
                task=task,
                event_history=history,
            )

            if verdict["label"] != "POTENTIAL_DONE":
                continue
            if verdict["confidence"] < suggest_threshold:
                continue

            candidate_payload = {
                "task_id": task["id"],
                "task_text": task["task"],
                "email_text": msg_text,
                "sender": msg.get("sender", ""),
                "thread_id": msg.get("thread_id", ""),
                "message_id": msg.get("message_id", ""),
                "retrieval_score": round(retrieval_score, 2),
                "llm_confidence": round(verdict["confidence"], 2),
                "reason": verdict["reason"],
                "evidence": verdict["evidence"],
            }
            if (
                best_for_message is None
                or candidate_payload["llm_confidence"] > best_for_message["llm_confidence"]
                or (
                    candidate_payload["llm_confidence"] == best_for_message["llm_confidence"]
                    and candidate_payload["retrieval_score"] > best_for_message["retrieval_score"]
                )
            ):
                best_for_message = candidate_payload

        if best_for_message:
            task_id = best_for_message["task_id"]
            existing = suggestions_by_task.get(task_id)
            if (
                existing is None
                or best_for_message["llm_confidence"] > existing["llm_confidence"]
                or (
                    best_for_message["llm_confidence"] == existing["llm_confidence"]
                    and best_for_message["retrieval_score"] > existing["retrieval_score"]
                )
            ):
                suggestions_by_task[task_id] = best_for_message

    return sorted(suggestions_by_task.values(), key=lambda x: x["llm_confidence"], reverse=True)


# ---------- pipeline ----------
def analyze_messages(messages, prefs, memory):
    results = []

    for i, msg in enumerate(messages):
        try:
            task = normalize_task(extract_task(msg))
            if not task or not task.get("task"):
                continue
            task["sender"] = msg.get("sender", "")
            task["thread_id"] = msg.get("thread_id", "")
            task["message_id"] = msg.get("message_id", "")
            task["timestamp"] = msg.get("timestamp", "")
            task, inferred = infer_missing_signals(task, prefs, memory)

            score, bucket, reasoning = score_task(task, prefs)
            results.append(
                {
                    "id": i,
                    "task": task["task"],
                    "score": score,
                    "bucket": bucket,
                    "predicted_bucket": bucket,
                    "reason": reasoning,
                    "meta": task,
                    "inferred": inferred,
                    "status": "open",
                    "manual_override": False,
                    "override_comment": "",
                    "source": "email",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            results.append(
                {
                    "id": i,
                    "task": f"Error processing message: {str(e)}",
                    "score": 0,
                    "bucket": "ERROR",
                    "predicted_bucket": "ERROR",
                    "reason": [],
                    "meta": {"task": "error"},
                    "inferred": {},
                    "status": "open",
                    "manual_override": False,
                    "override_comment": "",
                    "source": "email",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )

    return dedupe_results(results)
