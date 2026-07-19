#!/usr/bin/env bash
# Reset local first-run state and run the onboarding wizard for design/QA.
#
# Assumes a clean Postgres: wipes the Supabase DB volume, starts the stack,
# ensures the brokerai schema (SQLAlchemy create_all), then opens /setup.
#
# Usage:
#   ./scripts/dev-onboarding.sh                 Fresh DB + password admin wizard
#   ./scripts/dev-onboarding.sh --builtin       Same as default
#   ./scripts/dev-onboarding.sh --reset-only    Wipe DB volume + auth; do not start servers
#   ./scripts/dev-onboarding.sh --step exchange Open wizard forced to a step (DEV preview)
#   ./scripts/dev-onboarding.sh --no-supabase   Skip Docker wipe/start (you bring an empty DB)
#   ./scripts/dev-onboarding.sh --no-open       Do not open the browser
#
# Preview steps (DEV only): admin | exchange | instruments | data_sources | models | finish
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/venv"
ENV_FILE="${ROOT}/.env"
AUTH_DIR="${ROOT}/data/auth"
SUPA="${ROOT}/deploy/supabase"
SUPABASE_DB_CONTAINER="supabase-db"
PIDS=()

RESET_ONLY=false
NO_OPEN=false
NO_SUPABASE=false
PREVIEW_STEP=""
AUTH_MODE=builtin

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Start BrokerAI onboarding against a clean Postgres (from scratch).

Wipes the local Supabase DB volume, recreates the stack, ensures the brokerai
schema, clears data/auth/, then starts the wizard. Does not reset deploy/supabase/.env keys.

Options:
  --builtin          Use built-in password admin (default)
  --reset-only       Wipe DB volume + local auth; do not start API/Vite
  --step NAME        After start, open /setup?previewStep=NAME (DEV only)
                     NAME: admin | exchange | instruments | data_sources | models | finish
  --no-supabase      Skip Docker wipe/start; require an empty DB + BROKERAI_DATABASE_URL
  --no-open          Do not open the browser
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --builtin) AUTH_MODE=builtin; shift ;;
    --oidc)
      echo "Local Authelia OIDC was removed. Use built-in auth, or configure an external IdP" >&2
      echo "in .env (see docs/auth/self-hosted-oidc.md) and run the app with BROKERAI_AUTH_MODE=oidc." >&2
      exit 1
      ;;
    --reset-only) RESET_ONLY=true; shift ;;
    --step)
      PREVIEW_STEP="$2"
      shift 2
      ;;
    --no-supabase) NO_SUPABASE=true; shift ;;
    --no-open) NO_OPEN=true; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "${PREVIEW_STEP}" in
  "" | admin | exchange | instruments | data_sources | models | strategy | finish) ;;
  *)
    echo "Invalid --step: ${PREVIEW_STEP}" >&2
    echo "Use: admin | exchange | instruments | data_sources | models | finish" >&2
    exit 1
    ;;
esac

log() { echo "[dev-onboarding] $*"; }
warn() { echo "[dev-onboarding] WARN: $*" >&2; }

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
}

compose_supabase() {
  (
    cd "${SUPA}"
    docker compose -f docker-compose.yml -f docker-compose.brokerai.yml "$@"
  )
}

postgres_ready() {
  docker ps --format '{{.Names}}' | grep -qx "${SUPABASE_DB_CONTAINER}" \
    && docker exec "${SUPABASE_DB_CONTAINER}" pg_isready -U postgres >/dev/null 2>&1
}

wait_for_postgres() {
  local i
  log "Waiting for Postgres (${SUPABASE_DB_CONTAINER}) — first init can take a minute"
  for i in $(seq 1 120); do
    if postgres_ready; then
      # Give init scripts a moment after pg_isready flips true on a fresh volume.
      sleep 2
      if postgres_ready; then
        log "Postgres is ready"
        return 0
      fi
    fi
    sleep 1
  done
  warn "Postgres not ready after 120s — schema ensure may fail until the db is healthy"
  return 1
}

wipe_supabase_db() {
  log "Wiping Supabase Postgres volume (clean DB from scratch)"
  if [[ -f "${SUPA}/.env" ]]; then
    compose_supabase down --remove-orphans || true
  else
    warn "deploy/supabase/.env missing — compose down may be incomplete"
  fi

  # Bind-mounted data dirs (not Docker named volumes). Keep .env / JWT keys.
  for dir in "${SUPA}/volumes/db/data" "${SUPA}/volumes/storage"; do
    if [[ -e "${dir}" ]]; then
      log "Removing ${dir}"
      rm -rf "${dir}"
    fi
  done
}

start_supabase_clean() {
  if [[ "${NO_SUPABASE}" == "true" ]]; then
    log "Skipping Supabase Docker (--no-supabase); assuming empty Postgres + BROKERAI_DATABASE_URL"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for a clean Supabase DB. Install Docker Desktop, or pass --no-supabase." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running. Start Docker Desktop and re-run." >&2
    exit 1
  fi

  wipe_supabase_db
  log "Starting self-hosted Supabase on a fresh volume"
  "${ROOT}/scripts/setup-supabase.sh" --start
  wait_for_postgres
}

ensure_schema() {
  if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "venv missing — run ./scripts/dev.sh --setup first" >&2
    exit 1
  fi
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo ".env missing — cannot ensure schema" >&2
    exit 1
  fi
  load_env
  if [[ -z "${BROKERAI_DATABASE_URL:-}" ]]; then
    echo "BROKERAI_DATABASE_URL unset after Supabase setup — check repo .env" >&2
    exit 1
  fi
  log "Ensuring brokerai schema (SQLAlchemy create_all on empty DB)"
  (
    cd "${ROOT}"
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
    "${VENV}/bin/python" -c "import asyncio; from brokerai.db.indexes import ensure_indexes; asyncio.run(ensure_indexes())"
  )
}

reset_auth() {
  log "Resetting local auth / onboarding state (data/auth)"
  mkdir -p "${ROOT}/data" "${ROOT}/logs"
  if [[ -d "${AUTH_DIR}" ]]; then
    rm -rf "${AUTH_DIR}"
  fi
  mkdir -p "${AUTH_DIR}"
}

seed_preview_admin() {
  # Seed a password user so later API steps work without re-entering credentials.
  if [[ -z "${PREVIEW_STEP}" || "${PREVIEW_STEP}" == "admin" ]]; then
    return 0
  fi
  if [[ ! -x "${VENV}/bin/python" ]]; then
    warn "venv missing — cannot seed preview admin; run ./scripts/dev.sh --setup first"
    return 0
  fi

  log "Seeding preview admin (preview / BrokerAI!2026Preview) for step '${PREVIEW_STEP}'"
  load_env
  export BROKERAI_DATA_DIR="${ROOT}/data"
  export BROKERAI_SECRET_KEY="${BROKERAI_SECRET_KEY:-dev-onboarding-secret}"
  export BROKERAI_AUTH_MODE=builtin
  "${VENV}/bin/python" <<'PY'
from brokerai.auth import AuthStore, hash_password
from brokerai.auth.onboarding import OnboardingStore
from brokerai.config.settings import reload_settings

reload_settings()
store = AuthStore()
if not store.is_setup_complete():
    store.create_user("preview", hash_password("BrokerAI!2026Preview"))
OnboardingStore().init_after_admin()
print("Preview admin ready")
PY

  case "${PREVIEW_STEP}" in
    exchange) ;;
    instruments | strategy | finish)
      "${VENV}/bin/python" <<PY
from brokerai.auth.onboarding import OnboardingStore
from brokerai.config.settings import reload_settings
reload_settings()
store = OnboardingStore()
kwargs = {"current_step": "${PREVIEW_STEP}", "selected_exchange_id": "oanda"}
if "${PREVIEW_STEP}" in ("strategy", "finish"):
    kwargs["enabled_pairs"] = ["EUR/USD", "GBP/USD", "USD/JPY"]
if "${PREVIEW_STEP}" == "finish":
    kwargs["strategy_id"] = "preview-strategy"
    kwargs["strategy_name"] = "EMA Crossover"
store.update_progress(**kwargs)
print("Preview progress set to ${PREVIEW_STEP}")
PY
      ;;
  esac
}

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}

trap cleanup EXIT INT TERM

if [[ ! -x "${VENV}/bin/python" || ! -d "${ROOT}/frontend/node_modules" ]]; then
  log "Bootstrapping dependencies via scripts/dev.sh --setup"
  # Bootstrap deps without starting a DB we are about to wipe.
  "${ROOT}/scripts/dev.sh" --setup --no-open --no-supabase
fi

start_supabase_clean
ensure_schema
reset_auth

if [[ "${RESET_ONLY}" == "true" ]]; then
  log "Clean DB + schema + auth reset complete (servers not started)"
  exit 0
fi

load_env
export BROKERAI_AUTH_MODE=builtin
log "Using BROKERAI_AUTH_MODE=builtin for onboarding preview"

seed_preview_admin

cd "${ROOT}"
load_env
export BROKERAI_AUTH_MODE=builtin

log "Starting orchestrator"
BROKERAI_AUTH_MODE=builtin "${VENV}/bin/brokerai" run orchestrator &
PIDS+=("$!")

PORT="${BROKERAI_WEB_PORT:-1989}"
log "Starting API on port ${PORT} (auth=builtin)"
BROKERAI_AUTH_MODE=builtin "${VENV}/bin/uvicorn" brokerai.web.app:app \
  --reload \
  --reload-exclude '.env' \
  --host 127.0.0.1 \
  --port "${PORT}" &
PIDS+=("$!")

log "Starting Vite on port 5173"
(cd "${ROOT}/frontend" && npm run dev -- --host 127.0.0.1) &
PIDS+=("$!")

SETUP_URL="http://localhost:5173/setup"
if [[ -n "${PREVIEW_STEP}" ]]; then
  SETUP_URL="${SETUP_URL}?previewStep=${PREVIEW_STEP}"
fi

echo ""
echo "BrokerAI onboarding preview (clean DB)"
echo "  Wizard:   ${SETUP_URL}"
echo "  API:      http://127.0.0.1:${PORT}"
echo "  Postgres: 127.0.0.1:5432 (Supabase, fresh volume)"
echo "  Studio:   http://127.0.0.1:3000"
echo "  Auth:     builtin (+ Supabase Auth when configured)"
if [[ -n "${PREVIEW_STEP}" && "${PREVIEW_STEP}" != "admin" ]]; then
  echo "  Preview login: preview / BrokerAI!2026Preview"
fi
echo "  Ctrl+C to stop"
echo ""

if [[ "${NO_OPEN}" != "true" ]] && [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
  sleep 1.5
  open "${SETUP_URL}" 2>/dev/null || true
fi

wait -n 2>/dev/null || wait
