#!/usr/bin/env bash
# Configure BrokerAI .env for local OIDC development with Authelia.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
AUTHELIA_DIR="${ROOT}/deploy/authelia/dev"
CONTAINER="brokerai-authelia-dev"

log() {
  echo "[dev-oidc] $*"
}

warn() {
  echo "[dev-oidc] WARN: $*" >&2
}

ensure_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    log "Creating .env from config/config.env.example"
    cp "${ROOT}/config/config.env.example" "${ENV_FILE}"
    {
      echo ""
      echo "# Local development overrides"
      echo "BROKERAI_DATA_DIR=data"
      echo "BROKERAI_LOG_DIR=logs"
      echo "BROKERAI_AUTO_UPDATE=false"
      echo "BROKERAI_ENABLED_BOTS=secretary,broker,researcher"
      echo "BROKERAI_SECRET_KEY=$(openssl rand -hex 16)"
    } >>"${ENV_FILE}"
  fi
}

set_env_var() {
  local key="$1"
  local value="$2"
  "${ROOT}/venv/bin/python" - "${ENV_FILE}" "${key}" "${value}" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = env_path.read_text().splitlines() if env_path.exists() else []
out: list[str] = []
found = False
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n")
PY
}

configure_env() {
  local redirect_uri="http://localhost:5173/api/auth/oidc/callback"
  if [[ "${BACKEND_ONLY:-false}" == "true" ]]; then
    redirect_uri="http://127.0.0.1:1989/api/auth/oidc/callback"
  fi
  ensure_env_file
  log "Writing OIDC settings to .env"
  set_env_var "BROKERAI_AUTH_MODE" "oidc"
  set_env_var "BROKERAI_OIDC_ISSUER" "http://localhost:9091"
  set_env_var "BROKERAI_OIDC_CLIENT_ID" "brokerai"
  set_env_var "BROKERAI_OIDC_CLIENT_SECRET" "brokerai-dev-local-secret"
  set_env_var "BROKERAI_OIDC_REDIRECT_URI" "${redirect_uri}"
}

start_authelia() {
  if [[ "${CONFIGURE_ONLY:-false}" == "true" ]]; then
    log "Skipping Authelia container start (--configure-only)"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker not found — install Docker Desktop and re-run ./scripts/dev.sh --oidc"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    warn "Docker is not running — start Docker Desktop and re-run ./scripts/dev.sh --oidc"
    exit 1
  fi

  mkdir -p "${AUTHELIA_DIR}/config"
  touch "${AUTHELIA_DIR}/config/notification.txt"

  if docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    log "Authelia already running (${CONTAINER})"
    return 0
  fi

  log "Starting Authelia (${CONTAINER}) on http://localhost:9091"
  docker compose -f "${AUTHELIA_DIR}/docker-compose.yml" up -d

  local attempt
  for attempt in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:9091/.well-known/openid-configuration" >/dev/null 2>&1; then
      log "Authelia OIDC discovery is ready"
      return 0
    fi
    sleep 1
  done

  warn "Authelia did not become ready within 30s — check: docker logs ${CONTAINER}"
}

main() {
  BACKEND_ONLY=false
  CONFIGURE_ONLY=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --backend-only) BACKEND_ONLY=true; shift ;;
      --configure-only) CONFIGURE_ONLY=true; shift ;;
      *) shift ;;
    esac
  done
  configure_env
  start_authelia
  log "Local OIDC ready"
  log "  Authelia:  http://localhost:9091"
  log "  Dev user:  dev"
  log "  Password:  BrokerAI!2026"
}

main "$@"
