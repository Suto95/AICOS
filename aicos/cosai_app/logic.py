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
from .data import get_learned_weight

NOISE_SUBJECT_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bnewsletter\b",
    r"\bdigest\b",
    r"\bpromo\b",
    r"\bpromotion\b",
    r"\boffer\b",
    r"\bsale\b",
    r"\bdiscount\b",
    r"\bwebinar\b",
    r"\bevent reminder\b",
    r"\bno-reply\b",
    r"\bnotification\b",
]

ACTION_HINT_PATTERNS = [
    r"\bplease\b",
    r"\bcan you\b",
    r"\bneed\b",
    r"\brequired\b",
    r"\baction required\b",
    r"\bdeadline\b",
    r"\bdue\b",
    r"\bby (today|tomorrow|monday|tuesday|wednesday|thursday|friday)\b",
    r"\bapprove\b",
    r"\breview\b",
    r"\bfollow up\b",
    r"\brespond\b",
    r"\bsend\b",
    r"\bcomplete\b",
    r"\bsubmit\b",
    r"\bfix\b",
    r"\brequest\b",
    r"\breminder\b",
    r"\btodo\b",
    r"\bto do\b",
    r"\btask\b",
    r"\bmeeting\b",
    r"\binvoice\b",
]

STRONG_ACTION_PATTERNS = [
    r"\baction required\b",
    r"\brequired immediately\b",
    r"\bdeadline\b",
    r"\bdue (?:today|tomorrow|monday|tuesday|wednesday|thursday|friday)\b",
    r"\bby (?:today|tomorrow|monday|tuesday|wednesday|thursday|friday)\b",
    r"\bapprove\b",
    r"\bsubmit\b",
    r"\bfix\b",
]

MARKETING_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bnewsletter\b",
    r"\bpromo(?:tion)?\b",
    r"\boffer\b",
    r"\bsale\b",
    r"\bdiscount\b",
    r"\bwebinar\b",
]

NON_ACTION_PATTERNS = [
    r"\bno (?:further )?action (?:is )?(?:needed|required)?(?: from| for)? you\b",
    r"\bno (?:further )?action (?:is )?(?:needed|required)\b",
    r"\b(?:ignore|disregard) (?:my |the )?(?:previous|earlier) request\b",
    r"\b(?:task|work|review|migration|request) (?:is )?(?:complete|completed|finished)\b",
    r"\bcompleted successfully\b",
]

AMBIGUOUS_OWNER_PATTERNS = [
    r"\bcan someone\b",
    r"\bcould someone\b",
    r"\bcan anyone\b",
    r"\bcould anyone\b",
    r"\bnot sure who owns\b",
    r"\bwho (?:can|could|will) (?:own|handle|review|take)\b",
]


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
    for key in tuple(SIGNAL_FIELDS) + ("urgency_signal", "importance_signal"):
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


def _sender_domain(sender):
    raw = (sender or "").strip().lower()
    if not raw:
        return ""
    match = re.search(r"([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", raw)
    email = match.group(1) if match else raw
    if "@" not in email:
        return ""
    return email.split("@", 1)[1]


def derive_user_hint_profile(
    events,
    account_id=None,
    min_action_count=2,
    min_noise_count=2,
    min_noise_domain_count=2,
):
    action_token_counts = {}
    noise_token_counts = {}
    noise_sender_counts = {}

    for event in events or []:
        payload = event.get("payload") or {}
        event_account_id = payload.get("account_id")
        if account_id is not None and event_account_id is not None:
            try:
                if int(event_account_id) != int(account_id):
                    continue
            except (TypeError, ValueError):
                continue

        tokens = {t for t in tokenize_text(event.get("task_text", "")) if len(t) >= 4 and not t.isdigit()}
        event_type = event.get("event_type")

        if event_type == "task_created_manual":
            for t in tokens:
                action_token_counts[t] = action_token_counts.get(t, 0) + 1
            continue

        if event_type == "task_deleted":
            # Deletions from email-sourced tasks are strong noise signals.
            if payload.get("source") and payload.get("source") != "email":
                continue
            for t in tokens:
                noise_token_counts[t] = noise_token_counts.get(t, 0) + 1
            sender_domain = payload.get("sender_domain") or _sender_domain(payload.get("sender", ""))
            if sender_domain:
                noise_sender_counts[sender_domain] = noise_sender_counts.get(sender_domain, 0) + 1

    return {
        "action_tokens": {k for k, v in action_token_counts.items() if v >= min_action_count},
        "noise_tokens": {k for k, v in noise_token_counts.items() if v >= min_noise_count},
        "noise_sender_domains": {k for k, v in noise_sender_counts.items() if v >= min_noise_domain_count},
    }


def merge_hint_profiles(*profiles):
    merged = {
        "action_tokens": set(),
        "noise_tokens": set(),
        "noise_sender_domains": set(),
    }
    for p in profiles:
        if not p:
            continue
        merged["action_tokens"].update(p.get("action_tokens", set()))
        merged["noise_tokens"].update(p.get("noise_tokens", set()))
        merged["noise_sender_domains"].update(p.get("noise_sender_domains", set()))
    return merged


def build_compact_message_context(message, max_body_chars=500):
    subject = (message.get("subject") or message.get("text") or "").strip()
    snippet = (message.get("snippet") or "").strip()
    body = (message.get("body") or "").strip()
    if len(body) > max_body_chars:
        body = body[:max_body_chars]
    sender = (message.get("sender") or "").strip()

    parts = []
    if subject:
        parts.append(f"Subject: {subject}")
    if sender:
        parts.append(f"From: {sender}")
    if snippet:
        parts.append(f"Snippet: {snippet}")
    if body:
        parts.append(f"Body: {body}")
    return "\n".join(parts)


def is_task_like_message(message, hint_profile=None):
    subject = (message.get("subject") or message.get("text") or "").lower()
    snippet = (message.get("snippet") or "").lower()
    body = (message.get("body") or "").lower()
    sender = (message.get("sender") or "").lower()
    hay = " ".join([subject, snippet, sender])
    summary_context = " ".join([subject, snippet])
    full_context = " ".join([subject, snippet, body, sender])
    token_set = tokenize_text(f"{subject} {snippet}")
    sender_domain = _sender_domain(sender)
    has_action_phrase = any(re.search(p, hay) for p in ACTION_HINT_PATTERNS)
    has_strong_action = any(re.search(p, hay) for p in STRONG_ACTION_PATTERNS)

    if not hay.strip():
        return False

    # Corrections, completion notices, and unowned requests should not create work
    # for the recipient merely because they contain words such as "request" or "review".
    if any(re.search(p, summary_context) for p in NON_ACTION_PATTERNS):
        return False
    if any(re.search(p, summary_context) for p in AMBIGUOUS_OWNER_PATTERNS):
        return False

    # Marketing often uses weak calls to action ("please review", "see offer").
    # Only explicit operational language is allowed to override marketing signals.
    if any(re.search(p, full_context) for p in MARKETING_PATTERNS) and not has_strong_action:
        return False

    if hint_profile:
        action_overlap = token_set & hint_profile.get("action_tokens", set())
        noise_overlap = token_set & hint_profile.get("noise_tokens", set())
        noise_sender_domains = hint_profile.get("noise_sender_domains", set())

        if action_overlap:
            return True
        if sender_domain and sender_domain in noise_sender_domains and not has_action_phrase:
            return False
        if len(noise_overlap) >= 2 and not has_action_phrase:
            return False

    if any(re.search(p, hay) for p in NOISE_SUBJECT_PATTERNS):
        # Still allow if strong action words exist.
        return has_strong_action

    return has_action_phrase


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
    compact_text = build_compact_message_context(message)
    prompt = f"""
Extract structured task.

Message:
{compact_text}

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

    urgency_signal = IMPORTANCE_MAP.get(task.get("urgency_signal"))
    importance_signal = IMPORTANCE_MAP.get(task.get("importance_signal"))

    if urgency_signal is not None:
        urgency = 0.8 * urgency + 0.2 * urgency_signal
    if importance_signal is not None:
        importance = 0.8 * importance + 0.2 * importance_signal

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


# ---------- pipeline ----------
def analyze_messages(messages, prefs, memory, hint_profile=None):
    results = []

    filtered_messages = [m for m in messages if is_task_like_message(m, hint_profile=hint_profile)]

    for i, msg in enumerate(filtered_messages):
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
