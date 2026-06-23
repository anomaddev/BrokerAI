#!/usr/bin/env bash
# Copyright (c) 2021-2026 community-scripts ORG
# Author: anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI

source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)

APP="BrokerAI"
var_tags="${var_tags:-trading;bot;finance}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-8}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"
var_port="${var_port:-1989}"

BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_INSTALL_URL="${BROKERAI_INSTALL_URL:-https://raw.githubusercontent.com/anomaddev/BrokerAI/main/install/brokerai-install.sh}"

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

function update_script() {
  header_info
  check_container_storage
  check_container_resources

  if [[ ! -d /opt/brokerai ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  msg_info "Updating ${APP}"
  if [[ -x /opt/brokerai/scripts/auto-update.sh ]]; then
    /opt/brokerai/scripts/auto-update.sh --force
  else
    msg_error "auto-update.sh not found at /opt/brokerai/scripts/auto-update.sh"
    exit
  fi
  msg_ok "Updated ${APP}"
  exit
}

export BROKERAI_REPO BROKERAI_BRANCH
export APP
export FUNCTIONS_FILE_PATH

start
build_container
description

msg_ok "Completed Successfully!\n"
echo -e "${CREATING}${GN} BrokerAI Web UI: ${CL}http://${IP}:${var_port}${CL}\n"
