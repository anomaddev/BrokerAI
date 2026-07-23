#!/usr/bin/env bash
# Copyright (c) 2021-2026 anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI
#
# Standalone LXC/Debian installer — no dependency on community-scripts build.func.
# Run inside an existing Debian/Ubuntu container or VM.

set -euo pipefail

APP="BrokerAI"
BROKERAI_REPO="https://github.com/anomaddev/BrokerAI"
BROKERAI_BRANCH="main"
SKIP_CLONE=false

BROKERAI_INSTALL_DIR="/opt/brokerai"
BROKERAI_CONFIG_DIR="/etc/brokerai"
BROKERAI_DATA_DIR="/var/lib/brokerai/data"
BROKERAI_LOG_DIR="/var/log/brokerai"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

msg_info() { echo -e "${BLUE}⏳${NC} $*"; }
msg_ok() { echo -e "${GREEN}✔${NC} $*"; }
msg_warn() { echo -e "${YELLOW}⚠${NC} $*"; }
msg_error() { echo -e "${RED}✖${NC} $*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Standalone BrokerAI installer for Debian/Ubuntu.

Options:
  --repo URL       Git repository URL (default: ${BROKERAI_REPO})
  --branch NAME    Git branch to install (default: ${BROKERAI_BRANCH})
  --skip-clone     Skip git clone; use files already in ${BROKERAI_INSTALL_DIR}
  -h, --help       Show this help message

Optional environment:
  BROKERAI_ADMIN_USER       Admin username (lowercase, 3-32 chars)
  BROKERAI_ADMIN_PASSWORD   Strong password (12+ chars, mixed case, digit, special)
  BROKERAI_DOMAIN           Public hostname — installs Caddy TLS (e.g. brokerai.example.com)
  BROKERAI_SUPABASE_DOMAIN  Optional second hostname for Kong + Studio (host Caddy)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      BROKERAI_REPO="$2"
      shift 2
      ;;
    --branch)
      BROKERAI_BRANCH="$2"
      shift 2
      ;;
    --skip-clone)
      SKIP_CLONE=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      msg_error "Unknown option: $1"
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  msg_error "This script must be run as root."
fi

if [[ ! -f /etc/os-release ]]; then
  msg_error "Unsupported OS: /etc/os-release not found."
fi

# shellcheck source=/dev/null
source /etc/os-release
case "${ID:-}" in
  debian | ubuntu) ;;
  *)
    msg_error "Unsupported OS: ${ID:-unknown}. Debian or Ubuntu required."
    ;;
esac

msg_info "Updating package lists"
apt-get update -qq

msg_info "Installing dependencies"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  curl wget git python3 python3-venv python3-pip build-essential openssl \
  openssh-server gnupg ca-certificates
msg_ok "Dependencies installed"

msg_info "Installing Node.js (for frontend build)"
if ! command -v npm >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
fi
msg_ok "Node.js ready"

msg_info "Creating brokerai system user"
if ! id brokerai &>/dev/null; then
  useradd -r -s /usr/sbin/nologin -d "${BROKERAI_INSTALL_DIR}" brokerai
fi
msg_ok "Created brokerai user"

if [[ "${SKIP_CLONE}" == "true" ]]; then
  msg_warn "Skipping git clone — using existing files in ${BROKERAI_INSTALL_DIR}"
  if [[ ! -f "${BROKERAI_INSTALL_DIR}/pyproject.toml" ]]; then
    msg_error "No BrokerAI installation found at ${BROKERAI_INSTALL_DIR}"
  fi
else
  msg_info "Cloning BrokerAI (${BROKERAI_BRANCH})"
  if [[ -d "${BROKERAI_INSTALL_DIR}/.git" ]]; then
    cd "${BROKERAI_INSTALL_DIR}"
    git fetch origin "${BROKERAI_BRANCH}"
    git checkout "${BROKERAI_BRANCH}"
    git pull origin "${BROKERAI_BRANCH}"
  else
    git clone --depth 1 --branch "${BROKERAI_BRANCH}" "${BROKERAI_REPO}" "${BROKERAI_INSTALL_DIR}"
  fi
  msg_ok "Cloned BrokerAI"
fi

msg_info "Installing Docker + self-hosted Supabase"
# Docker must be available before Python venv so setup can write DATABASE_URL hints later.
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-supabase.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/setup-supabase.sh"
msg_ok "Supabase install scripts ready"

msg_info "Setting up Python virtual environment"
# shellcheck source=scripts/lib/install-common.sh
source "${BROKERAI_INSTALL_DIR}/scripts/lib/install-common.sh"
_brokerai_require_python311 || exit 1
cd "${BROKERAI_INSTALL_DIR}"
python3 -m venv venv
"${BROKERAI_INSTALL_DIR}/venv/bin/pip" install --upgrade pip -q
"${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -r requirements.txt -q
"${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -e . -q
msg_ok "Python environment ready"

msg_info "Building frontend"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
"${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
msg_ok "Frontend built"

msg_info "Configuring BrokerAI"
mkdir -p "${BROKERAI_CONFIG_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
_brokerai_seed_production_config \
  "${BROKERAI_CONFIG_DIR}" \
  "${BROKERAI_INSTALL_DIR}/config/config.env.example" \
  "${BROKERAI_DATA_DIR}" \
  "${BROKERAI_LOG_DIR}"
if [[ -n "${BROKERAI_DOMAIN:-}" ]]; then
  _brokerai_upsert_config_kv "${BROKERAI_CONFIG_DIR}/config.env" "BROKERAI_DOMAIN" "${BROKERAI_DOMAIN}"
fi
if [[ -n "${BROKERAI_SUPABASE_DOMAIN:-}" ]]; then
  _brokerai_upsert_config_kv "${BROKERAI_CONFIG_DIR}/config.env" "BROKERAI_SUPABASE_DOMAIN" "${BROKERAI_SUPABASE_DOMAIN}"
fi
msg_ok "Configured BrokerAI"

msg_info "Starting self-hosted Supabase (docker pull can take 10–30+ minutes; progress below)"
# setup-supabase.sh appends BROKERAI_DATABASE_URL to repo .env; also merge into production config.
# Pass public domains so GoTrue SITE_URL / SUPABASE_PUBLIC_URL match host Caddy when set.
# Keep this unsilenced — a quiet pull looks like a hang.
ENV_FILE="${BROKERAI_INSTALL_DIR}/.env" \
  BROKERAI_DOMAIN="${BROKERAI_DOMAIN:-}" \
  BROKERAI_SUPABASE_DOMAIN="${BROKERAI_SUPABASE_DOMAIN:-}" \
  bash "${BROKERAI_INSTALL_DIR}/scripts/lib/install-supabase.sh" "${BROKERAI_INSTALL_DIR}"
if [[ -f "${BROKERAI_INSTALL_DIR}/.env" ]]; then
  while IFS= read -r line; do
    case "${line}" in
      BROKERAI_DATABASE_URL=*|BROKERAI_SUPABASE_*=*)
        key="${line%%=*}"
        value="${line#*=}"
        _brokerai_upsert_config_kv "${BROKERAI_CONFIG_DIR}/config.env" "${key}" "${value}"
        ;;
    esac
  done <"${BROKERAI_INSTALL_DIR}/.env"
fi
(
  cd "${BROKERAI_INSTALL_DIR}"
  set -a
  # shellcheck disable=SC1091
  source "${BROKERAI_CONFIG_DIR}/config.env"
  set +a
  "${BROKERAI_INSTALL_DIR}/venv/bin/python" -c "import asyncio; from brokerai.db.indexes import ensure_indexes; asyncio.run(ensure_indexes())"
)
msg_ok "Supabase + schema ready"

msg_info "Configuring TLS (Caddy)"
_brokerai_maybe_install_caddy_tls "${BROKERAI_INSTALL_DIR}" "${BROKERAI_CONFIG_DIR}/config.env"
msg_ok "TLS configuration done"

BROKERAI_INSTALLED_COMMIT="$(git -C "${BROKERAI_INSTALL_DIR}" rev-parse HEAD)"

msg_info "Setting permissions"
mkdir -p /var/lib/brokerai/backups/postgres
chown -R brokerai:brokerai "${BROKERAI_INSTALL_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
chown -R root:brokerai "${BROKERAI_CONFIG_DIR}" /var/lib/brokerai/backups
chmod 750 "${BROKERAI_CONFIG_DIR}" /var/lib/brokerai/backups /var/lib/brokerai/backups/postgres
chmod 640 "${BROKERAI_CONFIG_DIR}/config.env"
# shellcheck source=scripts/lib/update-track.sh
source "${BROKERAI_INSTALL_DIR}/scripts/lib/update-track.sh"
_brokerai_ensure_git_safe_directory "${BROKERAI_INSTALL_DIR}"
msg_ok "Permissions set"

msg_info "Installing systemd services"
cp "${BROKERAI_INSTALL_DIR}/systemd/brokerai-orchestrator.service" /etc/systemd/system/
cp "${BROKERAI_INSTALL_DIR}/systemd/brokerai-web.service" /etc/systemd/system/
cp "${BROKERAI_INSTALL_DIR}/systemd/brokerai-update.service" /etc/systemd/system/
cp "${BROKERAI_INSTALL_DIR}/systemd/brokerai-update.timer" /etc/systemd/system/
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/auto-update.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/update-now.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/check-update.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/provision-admin-user.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/bootstrap-admin.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/backup-postgres.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-caddy.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/apply-domain-tls.sh"
ln -sf "${BROKERAI_INSTALL_DIR}/scripts/check-update.sh" /usr/local/bin/brokerai-check-update
ln -sf "${BROKERAI_INSTALL_DIR}/venv/bin/brokerai" /usr/local/bin/brokerai
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-update" /etc/sudoers.d/brokerai-update
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-admin" /etc/sudoers.d/brokerai-admin
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-power" /etc/sudoers.d/brokerai-power
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-domain" /etc/sudoers.d/brokerai-domain
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-services" /etc/sudoers.d/brokerai-services
chmod 440 /etc/sudoers.d/brokerai-update /etc/sudoers.d/brokerai-admin \
  /etc/sudoers.d/brokerai-power /etc/sudoers.d/brokerai-domain /etc/sudoers.d/brokerai-services
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/apply-domain-tls.sh"
visudo -cf /etc/sudoers.d/brokerai-update
visudo -cf /etc/sudoers.d/brokerai-admin
visudo -cf /etc/sudoers.d/brokerai-power
visudo -cf /etc/sudoers.d/brokerai-domain
visudo -cf /etc/sudoers.d/brokerai-services
_brokerai_install_postgres_backup "${BROKERAI_INSTALL_DIR}" "${BROKERAI_CONFIG_DIR}/config.env"
systemctl daemon-reload
systemctl enable --now brokerai-orchestrator brokerai-web brokerai-update.timer
msg_ok "Systemd services installed"

# shellcheck source=/dev/null
set -a && source "${BROKERAI_CONFIG_DIR}/config.env" && set +a
VERSION_FILE="/opt/${APP}_version.txt"
_brokerai_write_install_lock_from_config "${BROKERAI_INSTALLED_COMMIT}"

if systemctl is-active --quiet brokerai-orchestrator && systemctl is-active --quiet brokerai-web; then
  msg_ok "BrokerAI services running"
else
  msg_error "One or more BrokerAI services failed to start. Check: journalctl -u brokerai-orchestrator -u brokerai-web"
fi

if [[ -n "${BROKERAI_ADMIN_USER:-}" && -n "${BROKERAI_ADMIN_PASSWORD:-}" ]]; then
  msg_info "Bootstrapping BrokerAI admin account"
  export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD
  "${BROKERAI_INSTALL_DIR}/scripts/bootstrap-admin.sh"
  msg_ok "Admin account configured"
fi

_brokerai_install_container_update_command

WEB_PORT=$(grep -E '^BROKERAI_WEB_PORT=' "${BROKERAI_CONFIG_DIR}/config.env" | cut -d= -f2 || echo "1989")
DOMAIN=$(grep -E '^BROKERAI_DOMAIN=' "${BROKERAI_CONFIG_DIR}/config.env" | cut -d= -f2 || true)
SUPABASE_DOMAIN=$(grep -E '^BROKERAI_SUPABASE_DOMAIN=' "${BROKERAI_CONFIG_DIR}/config.env" | cut -d= -f2 || true)
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}${APP} installation complete.${NC}"
echo ""
if [[ -n "${DOMAIN}" ]]; then
  echo "  Web UI:     https://${DOMAIN}"
else
  echo "  Web UI:     http://${LOCAL_IP:-localhost}:${WEB_PORT:-1989}"
fi
if [[ -n "${SUPABASE_DOMAIN}" ]]; then
  echo "  Supabase:   https://${SUPABASE_DOMAIN} (Kong API; Studio basic auth)"
fi
echo "  Config:     ${BROKERAI_CONFIG_DIR}/config.env"
echo "  Backups:    /var/lib/brokerai/backups/postgres (timer: brokerai-postgres-backup.timer)"
echo "  Logs:       journalctl -u brokerai-orchestrator -u brokerai-web -f"
echo ""

msg_info "Cleaning up"
apt-get -y -qq autoremove
apt-get -y -qq autoclean
msg_ok "Done"
