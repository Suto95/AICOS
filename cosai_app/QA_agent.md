# AICOS QA Agent

## Purpose
The QA agent converts `CHANGELOG.md` changes into a test checklist, runs automated tests, and publishes a concise report with:
- total test cases
- automated coverage vs uncovered changes
- pass/fail/error summary

## What It Produces
- `qa_reports/latest_summary.md`
- `qa_reports/latest_summary.json`
- `qa_reports/bucket_sim_summary.md`
- `qa_reports/bucket_sim_summary.json`
- `qa_reports/bucket_sim_mismatches.jsonl`

## How To Run
From project root:

```bash
python3 tools/qa_agent.py
```

Run specific suites:

```bash
python3 tools/qa_agent.py --suites unit,integration,e2e,bucket_sim
python3 tools/qa_agent.py --suites bucket_sim
```

Optional:

```bash
python3 tools/qa_agent.py --changelog CHANGELOG.md --output-dir qa_reports
```

## Coverage Model
- Each changelog bullet becomes a QA test case.
- Cases are matched to automated test groups using keyword rules.
- Unmatched cases are flagged as manual coverage gaps.

## Current Automated Scope
- Unit:
  - Learning hints:
  - user-level and global hint profile derivation
  - profile merge behavior
  - task-like vs noise-like message decisions
  - Context/token optimizations:
  - compact email context trimming
  - Data layer:
  - cross-user event loading (`load_events_all_users`)
  - Config constants:
  - default Gmail filter

- Integration:
  - account DB flows (pending account creation, OAuth upsert, active account read)
  - OAuth state cache roundtrip
  - token security fallback behavior

- E2E (simulated with mocks, no external APIs):
  - end-to-end message filtering + hint merge + analysis pipeline path

- Bucket Simulation (offline deterministic harness):
  - fixture-driven dataset with task-like/noise/edge sections
  - exact bucket pass/fail validation (mock extraction default)
  - filter accuracy + bucket accuracy thresholds
  - per-bucket precision/recall-like metrics and confusion matrix

## Notes
- Browser-driven OAuth consent and full Streamlit UI behavior still require manual or Playwright/Selenium style E2E to reach full coverage.
