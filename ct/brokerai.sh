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
var_disk="${var_disk:-40}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"
# Docker-in-LXC (self-hosted Supabase) needs nesting + keyctl on unprivileged CTs.
var_nesting="${var_nesting:-1}"
var_keyctl="${var_keyctl:-1}"
var_port="${var_port:-1989}"

BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_INSTALL_URL="${BROKERAI_INSTALL_URL:-https://raw.githubusercontent.com/anomaddev/BrokerAI/main/install/brokerai-install.sh}"

# Optional pre-set admin (env: BROKERAI_ADMIN_USER / BROKERAI_ADMIN_PASSWORD or var_* aliases)
BROKERAI_ADMIN_USER="${BROKERAI_ADMIN_USER:-${var_brokerai_admin_user:-}}"
BROKERAI_ADMIN_PASSWORD="${BROKERAI_ADMIN_PASSWORD:-${var_brokerai_admin_password:-}}"
# Optional public hostname — installs host Caddy TLS inside the CT when set.
BROKERAI_DOMAIN="${BROKERAI_DOMAIN:-${var_brokerai_domain:-}}"
# Optional second hostname for public Kong/Studio (host Caddy; not compose Caddy).
BROKERAI_SUPABASE_DOMAIN="${BROKERAI_SUPABASE_DOMAIN:-${var_brokerai_supabase_domain:-}}"

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

_brokerai_can_prompt() {
  command -v whiptail >/dev/null 2>&1 && [[ -t 0 ]] && [[ "${TERM:-}" != "dumb" ]]
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

  if ! _brokerai_can_prompt; then
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

_brokerai_valid_domain() {
  [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] && [[ "$1" == *.* ]]
}

prompt_brokerai_domain() {
  if [[ -n "${BROKERAI_DOMAIN}" ]]; then
    if ! _brokerai_valid_domain "${BROKERAI_DOMAIN}"; then
      msg_error "Invalid BROKERAI_DOMAIN (use a hostname like brokerai.example.com)"
      exit 1
    fi
    prompt_brokerai_supabase_domain
    return 0
  fi

  if ! _brokerai_can_prompt; then
    return 0
  fi

  if ! whiptail --backtitle "BrokerAI Setup" --title "TLS hostname" \
    --yesno "Configure HTTPS with Caddy now?\n\nRequires DNS A/AAAA record(s) pointing at this container and ports 80/443 reachable for Let's Encrypt.\n\nChoose No to use plain HTTP on port ${var_port}." 14 74; then
    return 0
  fi

  while true; do
    local domain
    domain=$(whiptail --backtitle "BrokerAI Setup" --title "Public hostname" \
      --inputbox "Hostname for HTTPS (e.g. brokerai.example.com)" 10 70 \
      "${BROKERAI_DOMAIN:-}" 3>&1 1>&2 2>&3) || return 0
    if _brokerai_valid_domain "$domain"; then
      BROKERAI_DOMAIN="$domain"
      break
    fi
    whiptail --msgbox "Invalid hostname. Use a DNS name like brokerai.example.com." 10 70
  done

  export BROKERAI_DOMAIN
  prompt_brokerai_supabase_domain
}

prompt_brokerai_supabase_domain() {
  if [[ -n "${BROKERAI_SUPABASE_DOMAIN}" ]]; then
    if ! _brokerai_valid_domain "${BROKERAI_SUPABASE_DOMAIN}"; then
      msg_error "Invalid BROKERAI_SUPABASE_DOMAIN (use a hostname like supabase.example.com)"
      exit 1
    fi
    return 0
  fi

  if [[ -z "${BROKERAI_DOMAIN:-}" ]] || ! _brokerai_can_prompt; then
    return 0
  fi

  if ! whiptail --backtitle "BrokerAI Setup" --title "Supabase hostname" \
    --yesno "Also expose Supabase (Kong API + Studio) on a second HTTPS hostname?\n\nRequires a second DNS A/AAAA record and the same ports 80/443.\nStudio is protected with basic auth (DASHBOARD_* from Supabase .env).\n\nChoose No to keep Kong/Studio on loopback only." 16 74; then
    return 0
  fi

  # broker.example.com → supabase.example.com; foo.com → supabase.foo.com
  local suggested
  if [[ "${BROKERAI_DOMAIN}" == *.*.* ]]; then
    suggested="supabase.${BROKERAI_DOMAIN#*.}"
  else
    suggested="supabase.${BROKERAI_DOMAIN}"
  fi

  while true; do
    local domain
    domain=$(whiptail --backtitle "BrokerAI Setup" --title "Supabase hostname" \
      --inputbox "Hostname for Supabase Kong + Studio (e.g. supabase.example.com)" 10 70 \
      "${suggested}" 3>&1 1>&2 2>&3) || return 0
    if _brokerai_valid_domain "$domain"; then
      BROKERAI_SUPABASE_DOMAIN="$domain"
      break
    fi
    whiptail --msgbox "Invalid hostname. Use a DNS name like supabase.example.com." 10 70
  done

  export BROKERAI_SUPABASE_DOMAIN
}

bootstrap_brokerai_admin() {
  if [[ -z "${BROKERAI_ADMIN_USER:-}" || -z "${BROKERAI_ADMIN_PASSWORD:-}" || -z "${CTID:-}" ]]; then
    return 0
  fi

  if pct exec "$CTID" -- test -f /var/lib/brokerai/data/auth/users.json 2>/dev/null; then
    msg_ok "Admin account already configured — open Web UI to sign in"
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

# Ensure Caddy TLS is applied even if the in-CT install did not inherit BROKERAI_DOMAIN.
ensure_brokerai_domain() {
  if [[ -z "${BROKERAI_DOMAIN:-}" || -z "${CTID:-}" ]]; then
    return 0
  fi

  # Validate pre-set supabase domain when provided without interactive prompt.
  if [[ -n "${BROKERAI_SUPABASE_DOMAIN:-}" ]] && ! _brokerai_valid_domain "${BROKERAI_SUPABASE_DOMAIN}"; then
    msg_error "Invalid BROKERAI_SUPABASE_DOMAIN (use a hostname like supabase.example.com)"
    exit 1
  fi
  # When BROKERAI_DOMAIN was pre-set via env, still offer Supabase hostname prompt.
  if [[ -z "${BROKERAI_SUPABASE_DOMAIN:-}" ]]; then
    prompt_brokerai_supabase_domain
  fi

  msg_info "Configuring Caddy TLS for ${BROKERAI_DOMAIN}"
  local supabase_export=""
  if [[ -n "${BROKERAI_SUPABASE_DOMAIN:-}" ]]; then
    supabase_export="export BROKERAI_SUPABASE_DOMAIN=$(printf '%q' "${BROKERAI_SUPABASE_DOMAIN}")"
  fi
  # Timeout so a stuck ACME handshake cannot hang the Proxmox installer.
  pct exec "$CTID" -- bash -c "
    set -euo pipefail
    export BROKERAI_DOMAIN=$(printf '%q' "${BROKERAI_DOMAIN}")
    ${supabase_export}
    if ! timeout 120 bash -c '
      set -euo pipefail
      # shellcheck source=/dev/null
      source /opt/brokerai/scripts/lib/install-common.sh
      _brokerai_maybe_install_caddy_tls /opt/brokerai /etc/brokerai/config.env
    '; then
      echo 'Caddy TLS timed out — finish later via Settings → System → Public domains' >&2
    fi
    systemctl restart brokerai-web || true
  "
  if [[ -n "${BROKERAI_SUPABASE_DOMAIN:-}" ]]; then
    msg_ok "Caddy TLS ready — https://${BROKERAI_DOMAIN} + https://${BROKERAI_SUPABASE_DOMAIN}"
  else
    msg_ok "Caddy TLS ready — https://${BROKERAI_DOMAIN}"
  fi
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
prompt_brokerai_domain
export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD BROKERAI_DOMAIN BROKERAI_SUPABASE_DOMAIN
build_container
bootstrap_brokerai_admin
ensure_brokerai_domain
description

msg_ok "Completed Successfully!\n"
if [[ -n "${BROKERAI_DOMAIN:-}" ]]; then
  if [[ -n "${BROKERAI_ADMIN_USER:-}" ]]; then
    echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}https://${BROKERAI_DOMAIN}${CL} (login as ${BROKERAI_ADMIN_USER})\n"
  else
    echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}https://${BROKERAI_DOMAIN}${CL} (complete setup on first visit)\n"
  fi
  if [[ -n "${BROKERAI_SUPABASE_DOMAIN:-}" ]]; then
    echo -e "${CREATING}${GN} Supabase API/Studio: ${CL}https://${BROKERAI_SUPABASE_DOMAIN}${CL} (Studio basic auth)\n"
  fi
elif [[ -n "${BROKERAI_ADMIN_USER:-}" ]]; then
  echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}http://${IP}:${var_port}${CL} (login as ${BROKERAI_ADMIN_USER})\n"
else
  echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}http://${IP}:${var_port}${CL} (complete setup on first visit)\n"
fi
