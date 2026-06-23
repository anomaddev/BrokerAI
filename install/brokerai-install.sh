#!/usr/bin/env bash
# Copyright (c) 2021-2026 community-scripts ORG
# Author: anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"

BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_INSTALL_DIR="/opt/brokerai"
BROKERAI_CONFIG_DIR="/etc/brokerai"
BROKERAI_DATA_DIR="/var/lib/brokerai/data"
BROKERAI_LOG_DIR="/var/log/brokerai"

color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
$STD apt-get install -y \
  curl \
  wget \
  git \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  openssl \
  openssh-server \
  gnupg \
  ca-certificates
msg_ok "Installed Dependencies"

msg_info "Installing Node.js"
if ! command -v npm &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  $STD apt-get install -y nodejs
fi
msg_ok "Node.js ready"

msg_info "Creating brokerai system user"
if ! id brokerai &>/dev/null; then
  $STD useradd -r -s /usr/sbin/nologin -d "${BROKERAI_INSTALL_DIR}" brokerai
fi
msg_ok "Created brokerai user"

msg_info "Cloning BrokerAI (${BROKERAI_BRANCH})"
if [[ -d "${BROKERAI_INSTALL_DIR}/.git" ]]; then
  cd "${BROKERAI_INSTALL_DIR}"
  $STD git fetch origin "${BROKERAI_BRANCH}"
  $STD git checkout "${BROKERAI_BRANCH}"
  $STD git pull origin "${BROKERAI_BRANCH}"
else
  $STD git clone --depth 1 --branch "${BROKERAI_BRANCH}" "${BROKERAI_REPO}" "${BROKERAI_INSTALL_DIR}"
fi
msg_ok "Cloned BrokerAI"

msg_info "Installing MongoDB"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-mongodb.sh"
$STD bash "${BROKERAI_INSTALL_DIR}/scripts/lib/install-mongodb.sh"
msg_ok "MongoDB ready"

msg_info "Setting up Python virtual environment"
cd "${BROKERAI_INSTALL_DIR}"
$STD python3 -m venv venv
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install --upgrade pip
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -r requirements.txt
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -e .
msg_ok "Python environment ready"

msg_info "Building frontend"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
$STD "${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
msg_ok "Frontend built"

msg_info "Configuring BrokerAI"
mkdir -p "${BROKERAI_CONFIG_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
if [[ ! -f "${BROKERAI_CONFIG_DIR}/config.env" ]]; then
  cp "${BROKERAI_INSTALL_DIR}/config/config.env.example" "${BROKERAI_CONFIG_DIR}/config.env"
  SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c32)
  sed -i "s|^BROKERAI_SECRET_KEY=.*|BROKERAI_SECRET_KEY=${SECRET_KEY}|" "${BROKERAI_CONFIG_DIR}/config.env"
fi
msg_ok "Configured BrokerAI"

BROKERAI_INSTALLED_COMMIT="$(git -C "${BROKERAI_INSTALL_DIR}" rev-parse HEAD)"

msg_info "Setting permissions"
chown -R brokerai:brokerai "${BROKERAI_INSTALL_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
chown -R root:brokerai "${BROKERAI_CONFIG_DIR}"
chmod 750 "${BROKERAI_CONFIG_DIR}"
chmod 640 "${BROKERAI_CONFIG_DIR}/config.env"
# Root runs git for updates; repo is owned by brokerai after chown.
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
ln -sf "${BROKERAI_INSTALL_DIR}/scripts/check-update.sh" /usr/local/bin/brokerai-check-update
ln -sf "${BROKERAI_INSTALL_DIR}/venv/bin/brokerai" /usr/local/bin/brokerai
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-update" /etc/sudoers.d/brokerai-update
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-admin" /etc/sudoers.d/brokerai-admin
chmod 440 /etc/sudoers.d/brokerai-update /etc/sudoers.d/brokerai-admin
visudo -cf /etc/sudoers.d/brokerai-update
visudo -cf /etc/sudoers.d/brokerai-admin
$STD systemctl daemon-reload
$STD systemctl enable -q --now brokerai-orchestrator brokerai-web brokerai-update.timer
msg_ok "Installed systemd services"

# shellcheck source=/dev/null
set -a && source "${BROKERAI_CONFIG_DIR}/config.env" && set +a
VERSION_FILE="/opt/${APP}_version.txt"
_brokerai_write_install_lock_from_config "${BROKERAI_INSTALLED_COMMIT}"

if systemctl is-active --quiet brokerai-orchestrator && systemctl is-active --quiet brokerai-web; then
  msg_ok "BrokerAI services running"
else
  msg_error "One or more BrokerAI services failed to start"
  journalctl -u brokerai-orchestrator -u brokerai-web -n 20 --no-pager
  exit 1
fi

if [[ -n "${BROKERAI_ADMIN_USER:-}" && -n "${BROKERAI_ADMIN_PASSWORD:-}" ]]; then
  msg_info "Bootstrapping BrokerAI admin account"
  chmod +x "${BROKERAI_INSTALL_DIR}/scripts/bootstrap-admin.sh"
  export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD
  $STD "${BROKERAI_INSTALL_DIR}/scripts/bootstrap-admin.sh"
  msg_ok "Admin account configured"
fi

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"

cleanup_lxc
