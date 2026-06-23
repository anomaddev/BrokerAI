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
  openssl
msg_ok "Installed Dependencies"

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

msg_info "Setting up Python virtual environment"
cd "${BROKERAI_INSTALL_DIR}"
$STD python3 -m venv venv
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install --upgrade pip
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -r requirements.txt
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -e .
msg_ok "Python environment ready"

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
$STD systemctl daemon-reload
$STD systemctl enable -q --now brokerai-orchestrator brokerai-web
msg_ok "Installed systemd services"

RELEASE="$(cd "${BROKERAI_INSTALL_DIR}" && git rev-parse --short HEAD 2>/dev/null || echo "main")"
echo "${RELEASE}" >"/opt/${APP}_version.txt"

if systemctl is-active --quiet brokerai-orchestrator && systemctl is-active --quiet brokerai-web; then
  msg_ok "BrokerAI services running"
else
  msg_error "One or more BrokerAI services failed to start"
  journalctl -u brokerai-orchestrator -u brokerai-web -n 20 --no-pager
  exit 1
fi

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"

cleanup_lxc
