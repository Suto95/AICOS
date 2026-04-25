import os
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

import re

def safe_json_parse(content):
    try:
        return json.loads(content)
    except:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return None

load_dotenv()
client = OpenAI(api_key=os.getenv("OAI_API_KEY"))

# -----------------------------
# 1. SAMPLE INPUT (replace later with Slack/Gmail)
# -----------------------------
from gmail_ingest import fetch_emails

messages = fetch_emails(10)

# -----------------------------
# 2. TASK EXTRACTION (LLM)
# -----------------------------
def extract_task(message):
    prompt = f"""
Extract a structured task from this message.

Message: "{message['text']}"

Return JSON with:
- task
- deadline (YYYY-MM-DD or null)
- urgency_signal (low/medium/high or null)
- importance_signal (low/medium/high or null)

Also extract if mentioned:
- penalty_for_delay (yes/no/null)
- blocks_others (yes/no/null)
- outcome_value (low/medium/high/null)
- strategic_alignment (low/medium/high/null)
- reversibility (low/medium/high/null)
- visibility (low/medium/high/null)
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    content = response.choices[0].message.content
    task = safe_json_parse(content)
    if task is None:
        raise ValueError("Invalid or empty LLM response")
    return task

def find_missing_signals(task):
    missing = []

    # Urgency signals
    if not task.get("deadline"):
        missing.append("deadline")
    if task.get("penalty_for_delay") is None:
        missing.append("penalty_for_delay")
    if task.get("blocks_others") is None:
        missing.append("blocks_others")

    # Importance signals
    if task.get("outcome_value") is None:
        missing.append("outcome_value")
    if task.get("strategic_alignment") is None:
        missing.append("strategic_alignment")
    if task.get("reversibility") is None:
        missing.append("reversibility")
    if task.get("visibility") is None:
        missing.append("visibility")

    return missing

def ask_user_for_missing(task, task_id):
    print(f"\nTask {task_id}: {task['task']}")
    missing = find_missing_signals(task)

    for field in missing:
        if field == "deadline":
            val = input("Deadline (YYYY-MM-DD or Enter to skip): ")

        elif field == "penalty_for_delay":
            val = input("Is there a penalty for delay? (yes/no): ")

        elif field == "blocks_others":
            val = input("Does this block others? (yes/no): ")

        elif field == "outcome_value":
            val = input("Outcome value? (low/medium/high): ")

        elif field == "strategic_alignment":
            val = input("Strategic alignment? (low/medium/high): ")

        elif field == "reversibility":
            val = input("Reversibility? (low/medium/high): ")

        elif field == "visibility":
            val = input("Visibility? (low/medium/high): ")

        else:
            continue

        if val.strip():
            task[field] = val.strip().lower()

    return task

def generate_reasoning(task):
    prompt = f"""
Explain the reason for urgency_signal and importance_signal

Task: {task['task']}

Return reason in max 10 words.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()

# -----------------------------
# 3. FEATURE ENGINEERING
# -----------------------------
def compute_features(task):
    today = datetime(2026, 3, 29)

    # Deadline
    if task.get("deadline"):
        try:
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d")
            days = (deadline - today).days
        except:
            days = 3
    else:
        days = 5

    deadline_score = max(0, min(1, 1 / (days + 1)))

    # Urgency factors
    penalty = 1.0 if task.get("penalty_for_delay") == "yes" else 0.3
    blocking = 1.0 if task.get("blocks_others") == "yes" else 0.3

    urgency_score = 0.4 * deadline_score + 0.3 * penalty + 0.3 * blocking

    # Importance factors
    importance_map = {"low": 0.3, "medium": 0.6, "high": 1.0}

    outcome = importance_map.get(task.get("outcome_value"), 0.5)
    strategic = importance_map.get(task.get("strategic_alignment"), 0.5)
    reversibility = importance_map.get(task.get("reversibility"), 0.5)
    visibility = importance_map.get(task.get("visibility"), 0.5)

    importance_score = (
        0.35 * outcome +
        0.30 * strategic +
        0.20 * visibility +
        0.15 * (1 - reversibility)  # less reversible = more important
    )

    return urgency_score, importance_score


# -----------------------------
# 4. PRIORITIZATION
# -----------------------------
def prioritize(task, urgency, importance):
    score = 0.5 * urgency + 0.5 * importance

    if urgency >= 0.6 and importance >= 0.6:
        bucket = "DO NOW"
    elif urgency < 0.6 and importance >= 0.6:
        bucket = "SCHEDULE"
    elif urgency >= 0.6 and importance < 0.6:
        bucket = "DELEGATE"
    else:
        bucket = "ELIMINATE"

    return score, bucket


# -----------------------------
# 5. EXPLANATION ENGINE
# -----------------------------
def explain(task, urgency, importance):
    reasons = []

    if urgency > 0.7:
        reasons.append("High urgency due to deadline or language")
    if importance > 0.7:
        reasons.append("High importance based on task impact")
    if task["urgency_signal"] == "high":
        reasons.append("Explicit urgency mentioned")
    if task["importance_signal"] == "high":
        reasons.append("High-level or strategic task")

    return reasons


# -----------------------------
# 6. MAIN PIPELINE
# -----------------------------
results = []
print("Starting processing...")
print("Messages:", messages)

tasks_needing_reasoning = []

for i, msg in enumerate(messages):
    try:
        task = extract_task(msg)
        missing = find_missing_signals(task)
        if missing:
            print(f"\nTask '{task['task']}' is missing signals: {missing}")
            user_choice = input("Do you want to fill them? (y/n): ")
            if user_choice.lower() == "y":
                task = ask_user_for_missing(task, i)
        
        urgency, importance = compute_features(task)
        score, bucket = prioritize(task, urgency, importance)

        reasoning = explain(task, urgency, importance)

        if not reasoning:
            tasks_needing_reasoning.append((i, task))

        results.append({
            "id":i,
            "task": task["task"],
            "score": round(score, 2),
            "bucket": bucket,
            "reason": reasoning
        })

    except Exception as e:
        print("Error:", e)

# -----------------------------
# 7. OUTPUT
# -----------------------------
df = pd.DataFrame(results).sort_values(by="score", ascending=False)

print("\n=== PRIORITIZED TASKS ===\n")
print(df[["id", "task", "score", "bucket", "reason"]].to_string(index=False))

# find tasks with empty reasoning
no_reason_tasks = [r for r in results if not r["reason"]]

if no_reason_tasks:
    print("\nTasks without reasoning:", [r["id"] for r in no_reason_tasks])

    user_input = input(
        "Enter task IDs to generate reasoning (comma-separated), or press Enter to skip: "
    )

    if user_input.strip():
        selected_ids = [int(x.strip()) for x in user_input.split(",")]

        for r in results:
            if r["id"] in selected_ids:
                reasoning = generate_reasoning({"task": r["task"]})
                r["reason"] = [reasoning]

df = pd.DataFrame(results).sort_values(by="score", ascending=False)

print("\n=== UPDATED TASKS WITH REASONING ===\n")
print(df[["id", "task", "score", "bucket", "reason"]].to_string(index=False))