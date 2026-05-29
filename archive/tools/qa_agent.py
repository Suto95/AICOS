#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List


@dataclass
class ChangeCase:
    version: str
    section: str
    text: str
    tags: List[str]


@dataclass
class TestSuite:
    name: str
    path: Path
    tags: List[str]


AUTOMATION_RULES = [
    (r"hint learning|action/noise|noise|cross-user hint", "hints"),
    (r"default gmail fetch scope|in:inbox category:primary|gmail filter", "gmail_default_filter"),
    (r"event|task_events|event-history", "events"),
    (r"token usage|compact|context", "compact_context"),
    (r"oauth|pkce|scope mismatch|invalid_grant|google-first login|continue with google", "oauth"),
    (r"token protection|encryption|COSAI_ENCRYPTION_KEY", "security"),
    (r"account health", "account_health"),
    (r"migration|migrate local data", "migration"),
    (r"fetch controls changed from count-based to duration-based", "duration_window"),
    (r"rebrand|AICOS", "rebrand"),
    (r"multipage|streamlit", "ui_multipage"),
    (r"prioritization engine|bucket mapping|DO NOW|SCHEDULE|DELEGATE|REVIEW LATER|ELIMINATE", "bucket_logic"),
    (r"subject:cosai test|legacy hardcoded", "legacy_filter_regression"),
]


DEFAULT_SUITES = [
    TestSuite(
        name="unit",
        path=Path("tests/aicos"),
        tags=["hints", "events", "compact_context", "gmail_default_filter"],
    ),
    TestSuite(
        name="integration",
        path=Path("tests/aicos_integration"),
        tags=["oauth", "security", "migration", "account_health", "gmail_default_filter"],
    ),
    TestSuite(
        name="e2e",
        path=Path("tests/aicos_e2e"),
        tags=["hints", "events", "compact_context", "duration_window", "ui_multipage"],
    ),
    TestSuite(
        name="bucket_sim",
        path=Path("tools/simulate_buckets.py"),
        tags=["bucket_logic", "hints", "compact_context", "legacy_filter_regression", "duration_window"],
    ),
]


def parse_changelog_cases(changelog_path: Path) -> List[ChangeCase]:
    text = changelog_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    version = "Unversioned"
    section = "General"
    cases: List[ChangeCase] = []

    for line in lines:
        line = line.rstrip()
        if line.startswith("## "):
            version = line[3:].strip()
            section = "General"
            continue
        if line.startswith("### "):
            section = line[4:].strip()
            continue
        if line.startswith("- "):
            bullet = line[2:].strip()
            tags = []
            for pattern, tag in AUTOMATION_RULES:
                if re.search(pattern, bullet, flags=re.IGNORECASE):
                    tags.append(tag)
            cases.append(ChangeCase(version=version, section=section, text=bullet, tags=tags))
    return cases


def parse_test_output(output: str):
    ran = 0
    failures = 0
    errors = 0
    skipped = 0

    m_ran = re.search(r"Ran (\d+) tests? in", output)
    if m_ran:
        ran = int(m_ran.group(1))

    m_failed = re.search(r"FAILED \((.*?)\)", output)
    if m_failed:
        details = m_failed.group(1)
        m_failures = re.search(r"failures=(\d+)", details)
        m_errors = re.search(r"errors=(\d+)", details)
        if m_failures:
            failures = int(m_failures.group(1))
        if m_errors:
            errors = int(m_errors.group(1))

    m_skipped = re.search(r"OK \((.*?)\)", output)
    if m_skipped:
        details = m_skipped.group(1)
        m_skip_val = re.search(r"skipped=(\d+)", details)
        if m_skip_val:
            skipped = int(m_skip_val.group(1))

    return {"ran": ran, "failures": failures, "errors": errors, "skipped": skipped}


def run_suite(suite: TestSuite):
    if not suite.path.exists():
        return {
            "name": suite.name,
            "path": str(suite.path),
            "passed": False,
            "missing": True,
            "ran": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "raw_output": f"Suite path missing: {suite.path}",
        }

    if suite.name == "bucket_sim":
        cmd = [
            sys.executable,
            str(suite.path),
            "--mode",
            "mock_extract",
            "--fixtures",
            "tests/fixtures/aicos_bucket_sim_fixtures.json",
            "--output-dir",
            "qa_reports",
            "--min-bucket-accuracy",
            "85",
            "--min-filter-accuracy",
            "90",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return {
            "name": suite.name,
            "path": str(suite.path),
            "passed": proc.returncode == 0,
            "missing": False,
            "ran": 1,
            "failures": 0 if proc.returncode == 0 else 1,
            "errors": 0,
            "skipped": 0,
            "raw_output": out.strip(),
        }

    cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(suite.path), "-p", "test_*.py", "-v"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    parsed = parse_test_output(out)
    return {
        "name": suite.name,
        "path": str(suite.path),
        "passed": proc.returncode == 0,
        "missing": False,
        "ran": parsed["ran"],
        "failures": parsed["failures"],
        "errors": parsed["errors"],
        "skipped": parsed["skipped"],
        "raw_output": out.strip(),
    }


def compute_coverage(cases: List[ChangeCase], suites: List[TestSuite]):
    automated_tags = {tag for s in suites for tag in s.tags}
    mapped = []
    uncovered = []
    for c in cases:
        if c.tags and any(tag in automated_tags for tag in c.tags):
            mapped.append(c)
        else:
            uncovered.append(c)
    total = len(cases)
    pct = round((len(mapped) / total) * 100, 2) if total else 0.0
    return mapped, uncovered, pct


def build_summary(cases: List[ChangeCase], suites: List[TestSuite], suite_results: List[Dict]):
    mapped_cases, uncovered_cases, coverage_pct = compute_coverage(cases, suites)
    ran = sum(r["ran"] for r in suite_results)
    failures = sum(r["failures"] for r in suite_results)
    errors = sum(r["errors"] for r in suite_results)
    skipped = sum(r["skipped"] for r in suite_results)
    all_passed = all(r["passed"] for r in suite_results)

    return {
        "generated_at": datetime.now().isoformat(),
        "total_change_cases": len(cases),
        "automated_mapped_cases": len(mapped_cases),
        "uncovered_cases": len(uncovered_cases),
        "automated_coverage_pct": coverage_pct,
        "suite_results": [
            {
                "name": r["name"],
                "path": r["path"],
                "passed": r["passed"],
                "missing": r["missing"],
                "ran": r["ran"],
                "failures": r["failures"],
                "errors": r["errors"],
                "skipped": r["skipped"],
            }
            for r in suite_results
        ],
        "test_run": {
            "passed": all_passed,
            "ran": ran,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
        "uncovered_case_text": [f"[{c.version}::{c.section}] {c.text}" for c in uncovered_cases[:120]],
    }


def write_reports(output_dir: Path, summary: dict, suite_results: List[Dict]):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest_summary.json"
    md_path = output_dir / "latest_summary.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    status = "SUCCESS" if summary["test_run"]["passed"] else "FAILURE"
    md_lines = [
        "# AICOS QA Agent Report",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Overall status: **{status}**",
        "",
        "## Change Coverage",
        f"- Total changelog cases: **{summary['total_change_cases']}**",
        f"- Automated mapped cases: **{summary['automated_mapped_cases']}**",
        f"- Uncovered cases: **{summary['uncovered_cases']}**",
        f"- Automated coverage: **{summary['automated_coverage_pct']}%**",
        "",
        "## Test Execution (All Suites)",
        f"- Tests ran: **{summary['test_run']['ran']}**",
        f"- Failures: **{summary['test_run']['failures']}**",
        f"- Errors: **{summary['test_run']['errors']}**",
        f"- Skipped: **{summary['test_run']['skipped']}**",
        "",
        "## Suite Breakdown",
    ]

    for r in summary["suite_results"]:
        suite_status = "PASS" if r["passed"] else "FAIL"
        md_lines.append(
            f"- **{r['name']}** (`{r['path']}`): {suite_status} | "
            f"Ran: {r['ran']} | Failures: {r['failures']} | Errors: {r['errors']} | Skipped: {r['skipped']}"
        )
    md_lines.append("")

    if summary["uncovered_case_text"]:
        md_lines.append("## Uncovered Change Cases (Needs More Tests)")
        for case in summary["uncovered_case_text"]:
            md_lines.append(f"- {case}")
        md_lines.append("")

    md_lines.append("## Raw Outputs")
    for r in suite_results:
        md_lines.extend(
            [
                f"### {r['name']} ({r['path']})",
                "```text",
                r["raw_output"] or "(no output)",
                "```",
                "",
            ]
        )

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return md_path, json_path


def main():
    parser = argparse.ArgumentParser(description="AICOS QA agent: change-aware multi-suite testing and reporting.")
    parser.add_argument("--changelog", default="CHANGELOG.md", help="Path to changelog file.")
    parser.add_argument("--output-dir", default="qa_reports", help="Directory for QA reports.")
    parser.add_argument(
        "--suites",
        default="unit,integration,e2e,bucket_sim",
        help="Comma-separated suites to run: unit,integration,e2e,bucket_sim",
    )
    args = parser.parse_args()

    changelog_path = Path(args.changelog)
    output_dir = Path(args.output_dir)
    requested = {x.strip().lower() for x in args.suites.split(",") if x.strip()}

    if not changelog_path.exists():
        print(f"ERROR: changelog not found at {changelog_path}", file=sys.stderr)
        sys.exit(2)

    suites = [s for s in DEFAULT_SUITES if s.name in requested]
    if not suites:
        print("ERROR: no valid suites requested. Use unit,integration,e2e,bucket_sim", file=sys.stderr)
        sys.exit(2)

    cases = parse_changelog_cases(changelog_path)
    suite_results = [run_suite(s) for s in suites]
    summary = build_summary(cases, suites, suite_results)
    md_path, json_path = write_reports(output_dir, summary, suite_results)

    print(f"QA summary written to: {md_path}")
    print(f"QA json written to: {json_path}")
    print(
        f"Status: {'PASS' if summary['test_run']['passed'] else 'FAIL'} | "
        f"Ran: {summary['test_run']['ran']} | "
        f"Failures: {summary['test_run']['failures']} | "
        f"Errors: {summary['test_run']['errors']} | "
        f"Coverage: {summary['automated_coverage_pct']}%"
    )
    if not summary["test_run"]["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
