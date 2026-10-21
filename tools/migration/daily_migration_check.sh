#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORT_DIR="$ROOT_DIR/migration_reports"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="$REPORT_DIR/daily_check_$TIMESTAMP.log"

mkdir -p "$REPORT_DIR"

log() {
  printf '%s\n' "$1" | tee -a "$REPORT_FILE"
}

log "[daily-check] starting at $(date)"
log "[daily-check] repo root: $ROOT_DIR"

cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  log "[daily-check] activated virtualenv"
else
  log "[daily-check] warning: .venv not found"
fi

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
  log "[daily-check] loaded .env"
else
  log "[daily-check] warning: .env not found"
fi

log "[daily-check] running syntax compile checks"
python -m py_compile \
  aicos/cosai_app/auth.py \
  aicos/cosai_app/ui.py \
  aicos/cosai_app/logic.py \
  aicos/cosai_app/db.py

log "[daily-check] running import smoke checks"
PYTHONPATH=aicos python - <<'PY' >> "$REPORT_FILE" 2>&1
from aicos.cosai_app.logic import analyze_messages, extract_task
from aicos.cosai_app.db import init_db
from aicos.cosai_app.accounts import cache_oauth_verifier, pop_oauth_verifier

init_db()
cache_oauth_verifier(0, "migration-check", "ok")
assert pop_oauth_verifier(0, "migration-check") == "ok"
print("SMOKE_OK logic/db/accounts imports and verifier roundtrip")
PY

log "[daily-check] running migration API unit tests"
PYTHONPATH=. python -m unittest -q archive.tests.aicos_api.test_api_migration >> "$REPORT_FILE" 2>&1

if command -v pytest >/dev/null 2>&1; then
  log "[daily-check] running targeted tests"
  pytest -q \
    archive/tests/aicos/test_accounts_defaults.py \
    archive/tests/aicos/test_data_events.py \
    archive/tests/aicos/test_logic_hints.py \
    >> "$REPORT_FILE" 2>&1
else
  log "[daily-check] pytest not available; skipping targeted tests"
fi

log "[daily-check] complete at $(date)"
log "[daily-check] report: $REPORT_FILE"

printf '%s\n' "Daily migration check completed. Report: $REPORT_FILE"