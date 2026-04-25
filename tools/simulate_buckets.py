#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cosai_app.logic import (
    analyze_messages,
    derive_user_hint_profile,
    is_task_like_message,
    merge_hint_profiles,
)

BUCKETS = ["DO NOW", "SCHEDULE", "DELEGATE", "REVIEW LATER", "ELIMINATE", "FILTERED_OUT", "ERROR"]


def load_fixtures(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "task_like_emails": data.get("task_like_emails", []),
        "noise_emails": data.get("noise_emails", []),
        "edge_cases": data.get("edge_cases", []),
        "hint_events": data.get("hint_events", []),
    }


def to_message_obj(record: Dict):
    return {
        "text": record.get("subject", ""),
        "subject": record.get("subject", ""),
        "snippet": record.get("snippet", ""),
        "body": record.get("body", ""),
        "full_text": "\n".join([x for x in [record.get("subject", ""), record.get("snippet", ""), record.get("body", "")] if x]),
        "sender": record.get("sender", ""),
        "timestamp": record.get("timestamp", ""),
        "thread_id": record.get("thread_id", f"thread_{record.get('id', '')}"),
        "message_id": str(record.get("id", "")),
    }


def build_hint_profile(records: List[Dict]):
    events = []
    for rec in records:
        events.append(
            {
                "event_type": "task_created_manual",
                "task_text": rec.get("task_text", ""),
                "payload": {"account_id": rec.get("account_id", 1), "source": "manual"},
            }
        )
    user_profile = derive_user_hint_profile(events, account_id=1)
    global_profile = derive_user_hint_profile(events, account_id=1, min_action_count=5, min_noise_count=5, min_noise_domain_count=8)
    return merge_hint_profiles(user_profile, global_profile)


def evaluate_filters(records: List[Dict], hint_profile: Dict):
    results = []
    for rec in records:
        message = to_message_obj(rec)
        predicted = "task_like" if is_task_like_message(message, hint_profile=hint_profile) else "noise"
        expected = rec.get("expected_filter_decision")
        results.append(
            {
                "id": rec.get("id"),
                "expected_filter_decision": expected,
                "predicted_filter_decision": predicted,
                "pass": expected == predicted,
            }
        )
    return results


def run_analysis(records: List[Dict], hint_profile: Dict, mode: str):
    id_to_record = {str(r.get("id")): r for r in records}
    messages = [to_message_obj(r) for r in records]

    if mode == "live_extract":
        with patch("cosai_app.logic.dedupe_results", side_effect=lambda rows: rows):
            analyzed = analyze_messages(messages, prefs={}, memory=[], hint_profile=hint_profile)
    else:
        def fake_extract(message):
            rec = id_to_record.get(str(message.get("message_id", "")), {})
            return rec.get("mock_task") or {"task": rec.get("subject", "")}

        with patch("cosai_app.logic.extract_task", side_effect=fake_extract), patch(
            "cosai_app.logic.dedupe_results", side_effect=lambda rows: rows
        ):
            analyzed = analyze_messages(messages, prefs={}, memory=[], hint_profile=hint_profile)

    by_message_id = {}
    for row in analyzed:
        meta = row.get("meta", {})
        mid = str(meta.get("message_id", ""))
        if mid:
            by_message_id[mid] = row
    return analyzed, by_message_id


def compute_metrics(all_records: List[Dict], filter_results: List[Dict], analyzed_by_id: Dict):
    total_cases = len(all_records)
    filter_correct = sum(1 for r in filter_results if r["pass"])
    filter_accuracy = (filter_correct / total_cases) * 100 if total_cases else 0.0

    expected_task_like = [r for r in all_records if r.get("expected_filter_decision") == "task_like" and r.get("expected_bucket")]
    bucket_total = len(expected_task_like)
    bucket_correct = 0
    mismatches = []

    confusion = {expected: {pred: 0 for pred in BUCKETS} for expected in BUCKETS}

    for rec in expected_task_like:
        rid = str(rec.get("id"))
        expected_bucket = rec.get("expected_bucket")
        predicted_row = analyzed_by_id.get(rid)
        predicted_bucket = predicted_row.get("bucket") if predicted_row else "FILTERED_OUT"

        if expected_bucket not in confusion:
            confusion[expected_bucket] = {pred: 0 for pred in BUCKETS}
        if predicted_bucket not in confusion[expected_bucket]:
            confusion[expected_bucket][predicted_bucket] = 0
        confusion[expected_bucket][predicted_bucket] += 1

        if predicted_bucket == expected_bucket:
            bucket_correct += 1
            continue

        reason = "bucket_mismatch"
        if predicted_bucket == "FILTERED_OUT":
            reason = "filter_false_negative"
        elif predicted_bucket == "ERROR":
            reason = "analysis_error"

        mismatches.append(
            {
                "id": rid,
                "reason": reason,
                "expected_bucket": expected_bucket,
                "predicted_bucket": predicted_bucket,
                "subject": rec.get("subject", ""),
                "sender": rec.get("sender", ""),
                "notes": rec.get("notes", ""),
            }
        )

    # Noise false positives
    for rec in all_records:
        if rec.get("expected_filter_decision") != "noise":
            continue
        rid = str(rec.get("id"))
        if rid in analyzed_by_id:
            pred = analyzed_by_id[rid].get("bucket", "ERROR")
            mismatches.append(
                {
                    "id": rid,
                    "reason": "filter_false_positive",
                    "expected_bucket": None,
                    "predicted_bucket": pred,
                    "subject": rec.get("subject", ""),
                    "sender": rec.get("sender", ""),
                    "notes": rec.get("notes", ""),
                }
            )

    bucket_accuracy = (bucket_correct / bucket_total) * 100 if bucket_total else 0.0

    per_bucket = {}
    for bucket in ["DO NOW", "SCHEDULE", "DELEGATE", "REVIEW LATER", "ELIMINATE"]:
        tp = confusion.get(bucket, {}).get(bucket, 0)
        fp = sum(confusion.get(exp, {}).get(bucket, 0) for exp in confusion if exp != bucket)
        fn = sum(confusion.get(bucket, {}).get(pred, 0) for pred in confusion.get(bucket, {}) if pred != bucket)
        precision = (tp / (tp + fp) * 100) if (tp + fp) else 0.0
        recall = (tp / (tp + fn) * 100) if (tp + fn) else 0.0
        per_bucket[bucket] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision_pct": round(precision, 2),
            "recall_pct": round(recall, 2),
        }

    grouped = defaultdict(list)
    for m in mismatches:
        grouped[m["reason"]].append(m)
    top_mismatches = {k: v[:10] for k, v in grouped.items()}

    return {
        "total_cases": total_cases,
        "filter_accuracy_pct": round(filter_accuracy, 2),
        "bucket_accuracy_pct": round(bucket_accuracy, 2),
        "task_like_cases_for_bucket_eval": bucket_total,
        "per_bucket": per_bucket,
        "confusion_matrix": confusion,
        "mismatch_count": len(mismatches),
        "top_mismatches_by_reason": top_mismatches,
        "all_mismatches": mismatches,
    }


def write_reports(output_dir: Path, fixture_path: Path, mode: str, metrics: Dict, min_bucket_acc: float, min_filter_acc: float):
    output_dir.mkdir(parents=True, exist_ok=True)
    passed = metrics["bucket_accuracy_pct"] >= min_bucket_acc and metrics["filter_accuracy_pct"] >= min_filter_acc
    summary = {
        "generated_at": datetime.now().isoformat(),
        "mode": mode,
        "fixture_path": str(fixture_path),
        "thresholds": {"bucket_accuracy_pct": min_bucket_acc, "filter_accuracy_pct": min_filter_acc},
        "passed": passed,
        **{k: v for k, v in metrics.items() if k != "all_mismatches"},
    }

    summary_json = output_dir / "bucket_sim_summary.json"
    summary_md = output_dir / "bucket_sim_summary.md"
    mismatch_jsonl = output_dir / "bucket_sim_mismatches.jsonl"

    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with mismatch_jsonl.open("w", encoding="utf-8") as f:
        for row in metrics["all_mismatches"]:
            f.write(json.dumps(row) + "\n")

    lines = [
        "# AICOS Bucket Simulation Summary",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Mode: `{mode}`",
        f"- Fixtures: `{fixture_path}`",
        f"- Status: **{'PASS' if passed else 'FAIL'}**",
        "",
        "## Metrics",
        f"- Total cases: **{metrics['total_cases']}**",
        f"- Filter accuracy: **{metrics['filter_accuracy_pct']}%** (threshold {min_filter_acc}%)",
        f"- Bucket exact-match accuracy: **{metrics['bucket_accuracy_pct']}%** (threshold {min_bucket_acc}%)",
        f"- Task-like cases (bucket-evaluated): **{metrics['task_like_cases_for_bucket_eval']}**",
        f"- Total mismatches: **{metrics['mismatch_count']}**",
        "",
        "## Per-Bucket Precision/Recall",
    ]
    for b, vals in metrics["per_bucket"].items():
        lines.append(
            f"- {b}: precision {vals['precision_pct']}% | recall {vals['recall_pct']}% | tp {vals['tp']} fp {vals['fp']} fn {vals['fn']}"
        )
    lines.append("")
    lines.append("## Top Mismatches By Reason")
    for reason, rows in metrics["top_mismatches_by_reason"].items():
        lines.append(f"### {reason}")
        for row in rows:
            lines.append(
                f"- `{row['id']}` expected `{row.get('expected_bucket')}` got `{row.get('predicted_bucket')}` | {row.get('subject','')}"
            )
        lines.append("")
    summary_md.write_text("\n".join(lines), encoding="utf-8")

    return passed, summary_json, summary_md, mismatch_jsonl


def main():
    parser = argparse.ArgumentParser(description="Offline deterministic bucket simulation for AICOS.")
    parser.add_argument("--fixtures", default="tests/fixtures/aicos_bucket_sim_fixtures.json")
    parser.add_argument("--output-dir", default="qa_reports")
    parser.add_argument("--mode", choices=["mock_extract", "live_extract"], default="mock_extract")
    parser.add_argument("--min-bucket-accuracy", type=float, default=85.0)
    parser.add_argument("--min-filter-accuracy", type=float, default=90.0)
    args = parser.parse_args()

    fixture_path = Path(args.fixtures)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture file not found: {fixture_path}")

    fx = load_fixtures(fixture_path)
    all_records = fx["task_like_emails"] + fx["noise_emails"] + fx["edge_cases"]
    hint_profile = build_hint_profile(fx["hint_events"]) if fx["hint_events"] else None
    filter_results = evaluate_filters(all_records, hint_profile=hint_profile)
    _, analyzed_by_id = run_analysis(all_records, hint_profile=hint_profile, mode=args.mode)
    metrics = compute_metrics(all_records, filter_results, analyzed_by_id)
    passed, js, md, mm = write_reports(
        output_dir=Path(args.output_dir),
        fixture_path=fixture_path,
        mode=args.mode,
        metrics=metrics,
        min_bucket_acc=args.min_bucket_accuracy,
        min_filter_acc=args.min_filter_accuracy,
    )

    print(f"Bucket simulation summary written to: {md}")
    print(f"Bucket simulation json written to: {js}")
    print(f"Bucket simulation mismatches written to: {mm}")
    print(
        f"Status: {'PASS' if passed else 'FAIL'} | "
        f"filter_accuracy={metrics['filter_accuracy_pct']}% | "
        f"bucket_accuracy={metrics['bucket_accuracy_pct']}%"
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
