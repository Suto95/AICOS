#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="local"
FRONTEND_URL=""
ENV_FILE=""

usage() {
  cat <<'EOF'
Usage:
  ./tools/migration/predeploy_verify.sh [--mode local|production] [--frontend-url https://app.example.com/] [--env-file .env]

Examples:
  ./tools/migration/predeploy_verify.sh --mode local
  ./tools/migration/predeploy_verify.sh --mode production --frontend-url https://app.example.com/ --env-file .env.production
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
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

if [[ "$MODE" != "local" && "$MODE" != "production" ]]; then
  echo "Invalid mode: $MODE"
  exit 2
fi

cd "$ROOT_DIR"

if [[ -n "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "FAIL: env file not found: $ENV_FILE"
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

fail_count=0
warn_count=0

ok() {
  echo "OK: $1"
}

warn() {
  echo "WARN: $1"
  warn_count=$((warn_count + 1))
}

fail() {
  echo "FAIL: $1"
  fail_count=$((fail_count + 1))
}

require_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    fail "$name is missing"
  else
    ok "$name is set"
  fi
}

contains_value() {
  local list="$1"
  local needle="$2"
  IFS=',' read -r -a arr <<< "$list"
  for item in "${arr[@]}"; do
    if [[ "$(echo "$item" | xargs)" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

echo "[predeploy] mode=$MODE"

if [[ "$MODE" == "production" ]]; then
  require_var "COSAI_SESSION_SECRET"
  require_var "DATABASE_URL"
  require_var "COSAI_REDIRECT_URI"
  require_var "COSAI_API_CORS_ORIGINS"

  if [[ "${COSAI_SESSION_SECRET:-}" == "dev-insecure-session-secret-change-me" ]]; then
    fail "COSAI_SESSION_SECRET is using insecure dev fallback"
  fi

  env_marker="${COSAI_ENV:-${ENV:-}}"
  if [[ "$env_marker" != "production" ]]; then
    warn "COSAI_ENV/ENV is not set to production"
  else
    ok "COSAI_ENV/ENV is production"
  fi

  if [[ -n "$FRONTEND_URL" ]]; then
    if [[ "$FRONTEND_URL" != https://* ]]; then
      fail "frontend URL must use https in production"
    else
      ok "frontend URL uses https"
    fi

    if contains_value "${COSAI_REDIRECT_URI:-}" "$FRONTEND_URL"; then
      ok "COSAI_REDIRECT_URI contains frontend URL"
    else
      fail "COSAI_REDIRECT_URI is missing frontend URL"
    fi

    if contains_value "${COSAI_API_CORS_ORIGINS:-}" "$FRONTEND_URL"; then
      ok "COSAI_API_CORS_ORIGINS contains frontend URL"
    else
      fail "COSAI_API_CORS_ORIGINS is missing frontend URL"
    fi
  else
    warn "No --frontend-url supplied; skipping callback/CORS exact-match checks"
  fi
else
  require_var "COSAI_REDIRECT_URI"
  if [[ -n "${COSAI_SESSION_SECRET:-}" ]]; then
    ok "COSAI_SESSION_SECRET is set"
  else
    warn "COSAI_SESSION_SECRET is not set; dev fallback will be used"
  fi
fi

echo "[predeploy] failures=$fail_count warnings=$warn_count"

if [[ $fail_count -gt 0 ]]; then
  exit 1
fi

exit 0