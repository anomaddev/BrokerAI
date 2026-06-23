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

Optional environment (skip web setup wizard):
  BROKERAI_ADMIN_USER       Admin username (lowercase, 3-32 chars)
  BROKERAI_ADMIN_PASSWORD   Strong password (12+ chars, mixed case, digit, special)
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

msg_info "Installing MongoDB"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-mongodb.sh"
bash "${BROKERAI_INSTALL_DIR}/scripts/lib/install-mongodb.sh"
msg_ok "MongoDB ready"

msg_info "Setting up Python virtual environment"
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
if [[ ! -f "${BROKERAI_CONFIG_DIR}/config.env" ]]; then
  cp "${BROKERAI_INSTALL_DIR}/config/config.env.example" "${BROKERAI_CONFIG_DIR}/config.env"
  SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c32)
  sed -i "s|^BROKERAI_SECRET_KEY=.*|BROKERAI_SECRET_KEY=${SECRET_KEY}|" "${BROKERAI_CONFIG_DIR}/config.env"
fi
msg_ok "Configured BrokerAI"

msg_info "Setting permissions"
chown -R brokerai:brokerai "${BROKERAI_INSTALL_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
chown -R root:brokerai "${BROKERAI_CONFIG_DIR}"
chmod 750 "${BROKERAI_CONFIG_DIR}"
chmod 640 "${BROKERAI_CONFIG_DIR}/config.env"
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
ln -sf "${BROKERAI_INSTALL_DIR}/scripts/check-update.sh" /usr/local/bin/brokerai-check-update
ln -sf "${BROKERAI_INSTALL_DIR}/venv/bin/brokerai" /usr/local/bin/brokerai
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-update" /etc/sudoers.d/brokerai-update
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-admin" /etc/sudoers.d/brokerai-admin
chmod 440 /etc/sudoers.d/brokerai-update /etc/sudoers.d/brokerai-admin
visudo -cf /etc/sudoers.d/brokerai-update
visudo -cf /etc/sudoers.d/brokerai-admin
systemctl daemon-reload
systemctl enable --now brokerai-orchestrator brokerai-web brokerai-update.timer
msg_ok "Systemd services installed"

# shellcheck source=/dev/null
set -a && source "${BROKERAI_CONFIG_DIR}/config.env" && set +a
VERSION_FILE="/opt/${APP}_version.txt"
# shellcheck source=scripts/lib/update-track.sh
source "${BROKERAI_INSTALL_DIR}/scripts/lib/update-track.sh"
_brokerai_write_install_lock_from_config "$(cd "${BROKERAI_INSTALL_DIR}" && git rev-parse HEAD)"

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

WEB_PORT=$(grep -E '^BROKERAI_WEB_PORT=' "${BROKERAI_CONFIG_DIR}/config.env" | cut -d= -f2 || echo "1989")
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}${APP} installation complete.${NC}"
echo ""
echo "  Web UI:  http://${LOCAL_IP:-localhost}:${WEB_PORT:-1989}"
echo "  Config:  ${BROKERAI_CONFIG_DIR}/config.env"
echo "  Logs:    journalctl -u brokerai-orchestrator -u brokerai-web -f"
echo ""

msg_info "Cleaning up"
apt-get -y -qq autoremove
apt-get -y -qq autoclean
msg_ok "Done"
