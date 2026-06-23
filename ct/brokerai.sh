#!/usr/bin/env bash
# Copyright (c) 2021-2026 community-scripts ORG
# Author: anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI

source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)

APP="BrokerAI"
var_tags="${var_tags:-trading;bot;finance}"
var_cpu="${var_cpu:-4}"
var_ram="${var_ram:-8192}"
var_disk="${var_disk:-32}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"
var_port="${var_port:-1989}"

BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_INSTALL_URL="${BROKERAI_INSTALL_URL:-https://raw.githubusercontent.com/anomaddev/BrokerAI/main/install/brokerai-install.sh}"

# Optional pre-set admin (env: BROKERAI_ADMIN_USER / BROKERAI_ADMIN_PASSWORD or var_* aliases)
BROKERAI_ADMIN_USER="${BROKERAI_ADMIN_USER:-${var_brokerai_admin_user:-}}"
BROKERAI_ADMIN_PASSWORD="${BROKERAI_ADMIN_PASSWORD:-${var_brokerai_admin_password:-}}"

header_info "$APP"
variables
color
catch_errors

# Redirect install script fetch to this repo (build.func hardcodes ProxmoxVE install paths)
curl() {
  local url=""
  for arg in "$@"; do
    if [[ "$arg" == http* ]]; then
      url="$arg"
    fi
  done
  if [[ "$url" == *"/install/brokerai-install.sh" ]]; then
    command curl -fsSL "${BROKERAI_INSTALL_URL}"
    return $?
  fi
  command curl "$@"
}

_brokerai_valid_username() {
  [[ "$1" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]
}

_brokerai_valid_password() {
  local pw="$1"
  [[ ${#pw} -ge 12 ]] || return 1
  [[ "$pw" =~ [A-Z] ]] || return 1
  [[ "$pw" =~ [a-z] ]] || return 1
  [[ "$pw" =~ [0-9] ]] || return 1
  [[ "$pw" =~ [^A-Za-z0-9] ]] || return 1
  return 0
}

prompt_brokerai_admin() {
  if [[ -n "${BROKERAI_ADMIN_USER}" && -n "${BROKERAI_ADMIN_PASSWORD}" ]]; then
    if ! _brokerai_valid_username "${BROKERAI_ADMIN_USER}"; then
      msg_error "Invalid BROKERAI_ADMIN_USER (use lowercase letters, digits, _ or -)"
      exit 1
    fi
    if ! _brokerai_valid_password "${BROKERAI_ADMIN_PASSWORD}"; then
      msg_error "BROKERAI_ADMIN_PASSWORD does not meet strength requirements"
      exit 1
    fi
    return 0
  fi

  if ! command -v whiptail >/dev/null 2>&1; then
    return 0
  fi

  if ! whiptail --backtitle "BrokerAI Setup" --title "Admin account" \
    --yesno "Set up your BrokerAI login now?\n\nThis runs after your Proxmox install options (Default, Advanced, etc.) and before the container is created.\n\nChoose No to use the web setup wizard on first visit instead." 14 74; then
    return 0
  fi

  while true; do
    local user
    user=$(whiptail --backtitle "BrokerAI Setup" --title "Admin username" \
      --inputbox "Linux + web login name\n(lowercase, 3-32 chars)" 10 70 "${BROKERAI_ADMIN_USER:-admin}" 3>&1 1>&2 2>&3) || return 0
    if _brokerai_valid_username "$user"; then
      BROKERAI_ADMIN_USER="$user"
      break
    fi
    whiptail --msgbox "Invalid username. Use lowercase letters, digits, underscore, or hyphen." 10 70
  done

  while true; do
    local pw1 pw2
    pw1=$(whiptail --backtitle "BrokerAI Setup" --title "Admin password" \
      --passwordbox "Minimum 12 chars with upper, lower, digit, and special character" 10 70 3>&1 1>&2 2>&3) || return 0
    pw2=$(whiptail --backtitle "BrokerAI Setup" --title "Confirm password" \
      --passwordbox "Re-enter the password" 10 70 3>&1 1>&2 2>&3) || return 0
    if [[ "$pw1" != "$pw2" ]]; then
      whiptail --msgbox "Passwords do not match." 8 50
      continue
    fi
    if _brokerai_valid_password "$pw1"; then
      BROKERAI_ADMIN_PASSWORD="$pw1"
      break
    fi
    whiptail --msgbox "Password too weak. Use 12+ chars with upper, lower, digit, and special character." 10 70
  done

  export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD
}

bootstrap_brokerai_admin() {
  if [[ -z "${BROKERAI_ADMIN_USER:-}" || -z "${BROKERAI_ADMIN_PASSWORD:-}" || -z "${CTID:-}" ]]; then
    return 0
  fi

  msg_info "Bootstrapping BrokerAI admin account"
  local bootstrap_file
  bootstrap_file=$(mktemp)
  chmod 600 "$bootstrap_file"
  {
    printf 'BROKERAI_ADMIN_USER=%q\n' "$BROKERAI_ADMIN_USER"
    printf 'BROKERAI_ADMIN_PASSWORD=%q\n' "$BROKERAI_ADMIN_PASSWORD"
  } >"$bootstrap_file"

  pct push "$CTID" "$bootstrap_file" /root/brokerai-bootstrap.env
  pct exec "$CTID" -- chmod 600 /root/brokerai-bootstrap.env
  pct exec "$CTID" -- /opt/brokerai/scripts/bootstrap-admin.sh
  rm -f "$bootstrap_file"
  msg_ok "Admin account configured — open Web UI to sign in"
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources

  if [[ ! -d /opt/brokerai ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  msg_info "Updating ${APP}"
  /opt/brokerai/scripts/auto-update.sh --force
  msg_ok "Updated ${APP}"
  exit
}

export BROKERAI_REPO BROKERAI_BRANCH
export APP
export FUNCTIONS_FILE_PATH

start
prompt_brokerai_admin
export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD
build_container
bootstrap_brokerai_admin
description

msg_ok "Completed Successfully!\n"
if [[ -n "${BROKERAI_ADMIN_USER:-}" ]]; then
  echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}http://${IP}:${var_port}${CL} (login as ${BROKERAI_ADMIN_USER})\n"
else
  echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}http://${IP}:${var_port}${CL} (complete setup on first visit)\n"
fi
