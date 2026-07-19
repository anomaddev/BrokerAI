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
  ca-certificates \
  docker.io
$STD systemctl enable -q --now docker

# Debian 13 has no docker-compose-v2 package (Ubuntu name). Prefer apt plugin
# packages, then fall back to the official Compose CLI plugin binary.
msg_info "Installing Docker Compose plugin"
if docker compose version >/dev/null 2>&1; then
  msg_ok "Docker Compose already available"
elif $STD apt-get install -y docker-compose-plugin 2>/dev/null \
  || $STD apt-get install -y docker-compose-v2 2>/dev/null \
  || $STD apt-get install -y docker-compose 2>/dev/null; then
  msg_ok "Docker Compose installed from apt"
else
  mkdir -p /usr/local/lib/docker/cli-plugins
  arch="$(uname -m)"
  case "${arch}" in
    x86_64 | amd64) arch="x86_64" ;;
    aarch64 | arm64) arch="aarch64" ;;
    *) msg_error "Unsupported architecture for Docker Compose: ${arch}" ;;
  esac
  curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${arch}" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  msg_ok "Docker Compose plugin installed from GitHub"
fi
if ! docker compose version >/dev/null 2>&1; then
  msg_error "docker compose is required but not available after install"
fi
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

msg_info "Setting up Python virtual environment"
# shellcheck source=scripts/lib/install-common.sh
source "${BROKERAI_INSTALL_DIR}/scripts/lib/install-common.sh"
_brokerai_require_python311 || exit 1
cd "${BROKERAI_INSTALL_DIR}"
$STD python3 -m venv venv
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install --upgrade pip
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -r requirements.txt
$STD "${BROKERAI_INSTALL_DIR}/venv/bin/pip" install -e .
msg_ok "Python environment ready"

msg_info "Building frontend (npm install + Vite — often 2–5 minutes)"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
$STD "${BROKERAI_INSTALL_DIR}/scripts/build-frontend.sh"
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

# Do NOT wrap Supabase in $STD — docker compose pull downloads multi-GB images and
# looks like a hang when silenced. Keep pull/start progress visible in the console.
msg_info "Starting self-hosted Supabase (docker pull can take 10–30+ minutes)"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-supabase.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/setup-supabase.sh"
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
msg_info "Waiting for Postgres then applying schema"
(
  cd "${BROKERAI_INSTALL_DIR}"
  set -a
  # shellcheck disable=SC1091
  source "${BROKERAI_CONFIG_DIR}/config.env"
  set +a
  ready=0
  for _i in $(seq 1 90); do
    if docker exec supabase-db pg_isready -U postgres >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 2
  done
  if [[ "${ready}" -ne 1 ]]; then
    echo "Postgres did not become ready within 180s" >&2
    docker ps -a --filter name=supabase || true
    exit 1
  fi
  "${BROKERAI_INSTALL_DIR}/venv/bin/python" -c \
    "import asyncio; from brokerai.db.indexes import ensure_indexes; asyncio.run(ensure_indexes())"
)
msg_ok "Supabase + schema ready"

msg_info "Configuring TLS (Caddy)"
# ACME can retry when DNS is not ready; do not block the whole install forever.
if ! timeout 120 bash -c "
  # shellcheck disable=SC1091
  source '${BROKERAI_INSTALL_DIR}/scripts/lib/install-common.sh'
  export BROKERAI_DOMAIN='${BROKERAI_DOMAIN:-}'
  export BROKERAI_SUPABASE_DOMAIN='${BROKERAI_SUPABASE_DOMAIN:-}'
  _brokerai_maybe_install_caddy_tls '${BROKERAI_INSTALL_DIR}' '${BROKERAI_CONFIG_DIR}/config.env'
"; then
  echo "Caddy TLS step timed out or failed — finish later via Settings → System → Public domains" >&2
fi
msg_ok "TLS configuration done"

BROKERAI_INSTALLED_COMMIT="$(git -C "${BROKERAI_INSTALL_DIR}" rev-parse HEAD)"

msg_info "Setting permissions"
mkdir -p /var/lib/brokerai/backups/postgres
chown -R brokerai:brokerai "${BROKERAI_INSTALL_DIR}" "${BROKERAI_DATA_DIR}" "${BROKERAI_LOG_DIR}"
chown -R root:brokerai "${BROKERAI_CONFIG_DIR}" /var/lib/brokerai/backups
chmod 750 "${BROKERAI_CONFIG_DIR}" /var/lib/brokerai/backups /var/lib/brokerai/backups/postgres
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
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/backup-postgres.sh"
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/lib/install-caddy.sh"
ln -sf "${BROKERAI_INSTALL_DIR}/scripts/check-update.sh" /usr/local/bin/brokerai-check-update
ln -sf "${BROKERAI_INSTALL_DIR}/venv/bin/brokerai" /usr/local/bin/brokerai
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-update" /etc/sudoers.d/brokerai-update
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-admin" /etc/sudoers.d/brokerai-admin
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-power" /etc/sudoers.d/brokerai-power
cp "${BROKERAI_INSTALL_DIR}/config/sudoers/brokerai-domain" /etc/sudoers.d/brokerai-domain
chmod 440 /etc/sudoers.d/brokerai-update /etc/sudoers.d/brokerai-admin \
  /etc/sudoers.d/brokerai-power /etc/sudoers.d/brokerai-domain
chmod +x "${BROKERAI_INSTALL_DIR}/scripts/apply-domain-tls.sh"
visudo -cf /etc/sudoers.d/brokerai-update
visudo -cf /etc/sudoers.d/brokerai-admin
visudo -cf /etc/sudoers.d/brokerai-power
visudo -cf /etc/sudoers.d/brokerai-domain
_brokerai_install_postgres_backup "${BROKERAI_INSTALL_DIR}" "${BROKERAI_CONFIG_DIR}/config.env"
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
_brokerai_install_container_update_command

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"

cleanup_lxc
