"""
Archived done-detection helpers removed from the active app on 2026-09-28.

This module is intentionally not imported by the Streamlit app. It preserves
the prior retrieval and LLM-verdict approach for later optimization/review.
"""

import json
import re


def get_message_text_for_done(message):
    parts = [
        message.get("subject", ""),
        message.get("snippet", ""),
        message.get("body", ""),
        message.get("text", ""),
    ]
    return "\n".join([p for p in parts if p]).strip()


def message_dedupe_key(message, tokenize_text):
    message_id = (message.get("message_id") or "").strip()
    if message_id:
        return f"mid:{message_id}"

    thread_id = (message.get("thread_id") or "").strip()
    sender = (message.get("sender") or "").strip().lower()
    subject = (message.get("subject") or message.get("text") or "").strip().lower()
    text_sig = " ".join(sorted(tokenize_text(get_message_text_for_done(message))))[:180]
    return f"fallback:{thread_id}|{sender}|{subject}|{text_sig}"


def has_completion_keywords(message_text):
    completion_keywords = [
        r"\bdone\b",
        r"\bcompleted?\b",
        r"\bfinished\b",
        r"\bclosed\b",
        r"\bresolved\b",
        r"\bfixed\b",
        r"\bwrapped\s+up\b",
        r"\ball\s+set\b",
        r"\b(it'?s|this is|that is|we are|we're)\s+ready\b",
        r"\bdeployed\b",
        r"\blaunched\b",
    ]
    text_lower = message_text.lower()
    for pattern in completion_keywords:
        if re.search(pattern, text_lower):
            return True
    return False


def is_reply_message(message):
    subject = (message.get("subject") or "").lower().strip()
    is_reply_subject = subject.startswith(("re:", "fw:", "fwd:"))

    body = (message.get("body") or "").strip()
    first_lines = body.splitlines()[:5]
    has_quoted = any(
        line.lstrip().startswith(">")
        or "---" in line
        or "original message" in line.lower()
        for line in first_lines
    )

    return is_reply_subject or has_quoted


def retrieve_done_candidates(open_tasks, message, text_similarity, top_k=6, min_score=0.08):
    msg_text = get_message_text_for_done(message)
    msg_sender = message.get("sender", "")
    scored = []

    keyword_boost = 0.25 if has_completion_keywords(msg_text) else 0.0
    is_reply = is_reply_message(message)
    effective_min_score = 0.05 if is_reply else min_score

    for task in open_tasks:
        score = text_similarity(task.get("task", ""), msg_text)
        task_sender = task.get("meta", {}).get("sender", "")
        if task_sender and msg_sender and task_sender == msg_sender:
            score += 0.15
        score += keyword_boost

        if score >= effective_min_score:
            scored.append((score, task))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def llm_done_verdict(client, email_text, email_sender, task, event_history):
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
    content = response.choices[0].message.content
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        match = re.search(r"\{.*\}", content or "", re.DOTALL)
        parsed = json.loads(match.group()) if match else {}
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


def detect_done_suggestions(
    results,
    messages,
    client,
    text_similarity,
    tokenize_text,
    load_task_event_history,
    suggest_threshold=0.4,
    user_id=None,
):
    open_tasks = [r for r in results if r.get("status", "open") == "open"]
    suggestions_by_task = {}
    seen_messages = set()

    for msg in messages or []:
        dedupe_key = message_dedupe_key(msg, tokenize_text)
        if dedupe_key in seen_messages:
            continue
        seen_messages.add(dedupe_key)

        candidates = retrieve_done_candidates(open_tasks, msg, text_similarity, top_k=6, min_score=0.08)
        best_for_message = None

        for retrieval_score, task in candidates:
            history = load_task_event_history(task["id"], limit=8, user_id=user_id)
            msg_text = get_message_text_for_done(msg)
            verdict = llm_done_verdict(
                client=client,
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
