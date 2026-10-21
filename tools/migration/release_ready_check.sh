#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_URL=""
ENV_FILE=".env.production"

usage() {
  cat <<'EOF'
Usage:
  ./tools/migration/release_ready_check.sh --frontend-url https://your-frontend-domain.com/ [--env-file .env.production]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend-url)
      FRONTEND_URL="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$FRONTEND_URL" ]]; then
  echo "FAIL: --frontend-url is required"
  usage
  exit 2
fi

cd "$ROOT_DIR"

echo "[release-check] repo status"
git status --short

echo "[release-check] backend tests"
PYTHONPATH=. .venv/bin/python -m unittest -q archive.tests.aicos_api.test_api_migration

echo "[release-check] frontend build"
if command -v npm >/dev/null 2>&1; then
  (
    cd web
    npm run build
  )
else
  echo "WARN: npm not found; skipping frontend build"
fi

echo "[release-check] production predeploy verification"
./tools/migration/predeploy_verify.sh --mode production --frontend-url "$FRONTEND_URL" --env-file "$ENV_FILE"

echo "[release-check] SUCCESS"
