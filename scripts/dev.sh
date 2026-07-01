#!/usr/bin/env bash
# BrokerAI local development — bootstrap and run all dev services on macOS/Linux.
#
# Usage:
#   ./scripts/dev.sh              Start dev stack (bootstrap if needed)
#   ./scripts/dev.sh --setup      Bootstrap only (venv, .env, mongo, npm)
#   ./scripts/dev.sh --backend-only   API + orchestrator only (no Vite)
#   ./scripts/dev.sh --no-mongo   Skip MongoDB Docker container
#   ./scripts/dev.sh --no-open    Do not open browser (macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/venv"
ENV_FILE="${ROOT}/.env"
MONGO_CONTAINER="brokerai-mongo"
PIDS=()

SETUP_ONLY=false
NO_MONGO=false
NO_OPEN=false
BACKEND_ONLY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Bootstrap and run BrokerAI locally for development.

Options:
  --setup          Bootstrap venv, .env, MongoDB, and npm deps; do not start servers
  --no-mongo       Skip Docker MongoDB auto-start
  --no-open        Do not open the browser (macOS)
  --backend-only   Skip Vite; serve built static via uvicorn only
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup) SETUP_ONLY=true; shift ;;
    --no-mongo) NO_MONGO=true; shift ;;
    --no-open) NO_OPEN=true; shift ;;
    --backend-only) BACKEND_ONLY=true; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

log() {
  echo "[dev] $*"
}

warn() {
  echo "[dev] WARN: $*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

python_version_ok() {
  local py="$1"
  "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

find_python() {
  if command -v python3 >/dev/null 2>&1 && python_version_ok python3; then
    echo python3
    return 0
  fi
  if command -v python3.11 >/dev/null 2>&1 && python_version_ok python3.11; then
    echo python3.11
    return 0
  fi
  return 1
}

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
}

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

ensure_venv() {
  local py
  py="$(find_python)" || {
    echo "Python 3.11+ is required." >&2
    exit 1
  }

  if [[ ! -d "${VENV}" ]]; then
    log "Creating virtual environment"
    "$py" -m venv "${VENV}"
  fi

  log "Installing Python dependencies"
  "${VENV}/bin/pip" install -q --upgrade pip
  "${VENV}/bin/pip" install -q -r "${ROOT}/requirements.txt"
  "${VENV}/bin/pip" install -q -e "${ROOT}"
}

ensure_env_file() {
  if [[ -f "${ENV_FILE}" ]]; then
    return 0
  fi

  log "Creating .env from config/config.env.example"
  cp "${ROOT}/config/config.env.example" "${ENV_FILE}"
  {
    echo ""
    echo "# Local development overrides"
    echo "BROKERAI_DATA_DIR=data"
    echo "BROKERAI_LOG_DIR=logs"
    echo "BROKERAI_AUTO_UPDATE=false"
    echo "BROKERAI_ENABLED_BOTS=secretary,broker,researcher"
    echo "BROKERAI_USE_SECRETARY_PIPELINE=true"
    echo "BROKERAI_SECRET_KEY=$(openssl rand -hex 16)"
  } >>"${ENV_FILE}"
}

ensure_dirs() {
  mkdir -p "${ROOT}/data" "${ROOT}/logs"
}

ensure_mongo() {
  if [[ "${NO_MONGO}" == "true" ]]; then
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker not found — skipping MongoDB (install Docker Desktop for Mac)"
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    warn "Docker is not running — start Docker Desktop and re-run, or use --no-mongo"
    return 0
  fi

  if docker ps --format '{{.Names}}' | grep -qx "${MONGO_CONTAINER}"; then
    log "MongoDB container already running (${MONGO_CONTAINER})"
    return 0
  fi

  if docker ps -a --format '{{.Names}}' | grep -qx "${MONGO_CONTAINER}"; then
    log "Starting MongoDB container (${MONGO_CONTAINER})"
    docker start "${MONGO_CONTAINER}" >/dev/null
    return 0
  fi

  log "Creating MongoDB container (${MONGO_CONTAINER})"
  docker run -d --name "${MONGO_CONTAINER}" -p 27017:27017 mongo:7 >/dev/null
}

ensure_frontend_deps() {
  if [[ "${SETUP_ONLY}" == "true" || ! -d "${ROOT}/frontend/node_modules" ]]; then
    log "Installing frontend dependencies"
    (cd "${ROOT}/frontend" && npm ci --silent 2>/dev/null || npm install --silent)
  fi
}

ensure_static_build() {
  if [[ -f "${ROOT}/src/brokerai/web/static/index.html" ]]; then
    return 0
  fi
  log "Building frontend for backend-only mode"
  "${ROOT}/scripts/build-frontend.sh"
}

preflight() {
  if [[ "${BACKEND_ONLY}" != "true" ]]; then
    require_cmd npm
  fi
  if [[ "$(uname -s)" != "Darwin" && "$(uname -s)" != "Linux" ]]; then
    warn "Unsupported OS — continuing anyway"
  fi
}

bootstrap() {
  preflight
  ensure_venv
  ensure_env_file
  ensure_dirs
  ensure_mongo
  if [[ "${BACKEND_ONLY}" != "true" ]]; then
    ensure_frontend_deps
  fi
}

start_orchestrator() {
  log "Starting orchestrator"
  "${VENV}/bin/brokerai" run orchestrator &
  PIDS+=("$!")
}

start_api() {
  local port="${BROKERAI_WEB_PORT:-1989}"
  log "Starting API on port ${port}"
  "${VENV}/bin/uvicorn" brokerai.web.app:app \
    --reload \
    --reload-exclude '.env' \
    --host 127.0.0.1 \
    --port "${port}" &
  PIDS+=("$!")
}

start_vite() {
  log "Starting Vite dev server on port 5173"
  (cd "${ROOT}/frontend" && npm run dev -- --host 127.0.0.1) &
  PIDS+=("$!")
}

open_browser() {
  if [[ "${NO_OPEN}" == "true" || "${BACKEND_ONLY}" == "true" ]]; then
    return 0
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    sleep 1
    open "http://localhost:5173" 2>/dev/null || true
  fi
}

print_banner() {
  local port="${BROKERAI_WEB_PORT:-1989}"
  echo ""
  echo "BrokerAI dev running"
  if [[ "${BACKEND_ONLY}" == "true" ]]; then
    echo "  UI:      http://127.0.0.1:${port}"
  else
    echo "  UI:      http://localhost:5173  (Vite, hot reload)"
    echo "  API:     http://127.0.0.1:${port}"
  fi
  echo "  MongoDB: mongodb://127.0.0.1:27017/brokerai"
  echo "  Ctrl+C to stop all"
  echo ""
}

bootstrap
load_env

if [[ "${SETUP_ONLY}" == "true" ]]; then
  log "Setup complete"
  exit 0
fi

cd "${ROOT}"

if [[ "${BACKEND_ONLY}" == "true" ]]; then
  ensure_static_build
fi

start_orchestrator
start_api
if [[ "${BACKEND_ONLY}" != "true" ]]; then
  start_vite
fi

print_banner
open_browser

wait -n 2>/dev/null || wait
