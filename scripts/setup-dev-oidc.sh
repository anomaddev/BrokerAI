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
  ensure_env_file
  log "Writing OIDC settings to .env"
  set_env_var "BROKERAI_AUTH_MODE" "oidc"
  set_env_var "BROKERAI_OIDC_ISSUER" "https://127.0.0.1:9091"
  set_env_var "BROKERAI_OIDC_CLIENT_ID" "brokerai"
  set_env_var "BROKERAI_OIDC_CLIENT_SECRET" "brokerai-dev-local-secret"
  set_env_var "BROKERAI_OIDC_TLS_VERIFY" "false"
  if [[ "${BACKEND_ONLY:-false}" == "true" ]]; then
    set_env_var "BROKERAI_OIDC_REDIRECT_URI" "http://127.0.0.1:1989/api/auth/oidc/callback"
  else
    # Leave unset so the callback host matches the UI (localhost vs 127.0.0.1).
    set_env_var "BROKERAI_OIDC_REDIRECT_URI" ""
  fi
}

ensure_dev_tls_certs() {
  local cert_dir="${AUTHELIA_DIR}/config/certs"
  mkdir -p "${cert_dir}"
  if [[ -f "${cert_dir}/cert.pem" && -f "${cert_dir}/key.pem" ]]; then
    return 0
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    warn "openssl not found — cannot generate Authelia dev TLS certificate"
    exit 1
  fi
  log "Generating self-signed TLS certificate for 127.0.0.1 (dev only)"
  openssl req -x509 -newkey rsa:2048 \
    -keyout "${cert_dir}/key.pem" \
    -out "${cert_dir}/cert.pem" \
    -days 3650 -nodes \
    -subj "/CN=127.0.0.1" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    >/dev/null 2>&1
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
  ensure_dev_tls_certs

  if docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    if curl -sfk "https://127.0.0.1:9091/.well-known/openid-configuration" >/dev/null 2>&1; then
      log "Authelia already running (${CONTAINER})"
      return 0
    fi
    log "Authelia container is not healthy — recreating"
    docker compose -f "${AUTHELIA_DIR}/docker-compose.yml" down >/dev/null 2>&1 || true
  fi

  log "Starting Authelia (${CONTAINER}) on https://127.0.0.1:9091"
  docker compose -f "${AUTHELIA_DIR}/docker-compose.yml" up -d

  local attempt
  for attempt in $(seq 1 30); do
    if curl -sfk "https://127.0.0.1:9091/.well-known/openid-configuration" >/dev/null 2>&1; then
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
  log "  Authelia:  https://127.0.0.1:9091"
  log "  Dev user:  dev"
  log "  Password:  BrokerAI!2026"
}

main "$@"
