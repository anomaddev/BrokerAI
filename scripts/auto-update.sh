#!/usr/bin/env bash
# Copyright (c) 2021-2026 anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI
#
# Pulls latest code from GitHub, refreshes dependencies, and restarts services.
# Runs automatically via brokerai-update.timer, or manually with --force.
#
# Update track modes (Swift Package Manager-style):
#   branch         — latest commit on BROKERAI_BRANCH (default)
#   release        — pinned to BROKERAI_RELEASE tag (e.g. 0.1.0)
#   latest-release — newest GitHub release tag
#   next-major     — newest release within the installed major version

set -euo pipefail

APP="BrokerAI"
INSTALL_DIR="/opt/brokerai"
CONFIG_DIR="/etc/brokerai"
CONFIG_FILE="${CONFIG_DIR}/config.env"
VERSION_FILE="/opt/${APP}_version.txt"
LOG_DIR="/var/log/brokerai"
LOG_FILE="${LOG_DIR}/update.log"
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)"

FORCE=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Check for and apply BrokerAI updates from GitHub.

Update tracks (set in /etc/brokerai/config.env):
  branch          Latest commit on BROKERAI_BRANCH
  release         Pinned to BROKERAI_RELEASE (e.g. 0.1.0 or v0.1.0)
  latest-release  Newest GitHub release tag
  next-major      Newest release within installed major version

Options:
  --force   Run even if BROKERAI_AUTO_UPDATE=false
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

log() {
  local line
  line="$(date -Iseconds) $*"
  echo "${line}"
  echo "${line}" >>"${LOG_FILE}"
}

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck source=/dev/null
  set -a
  source "${CONFIG_FILE}"
  set +a
fi

BROKERAI_AUTO_UPDATE="${BROKERAI_AUTO_UPDATE:-true}"
BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_UPDATE_TRACK="${BROKERAI_UPDATE_TRACK:-branch}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_RELEASE="${BROKERAI_RELEASE:-}"

# shellcheck source=lib/update-track.sh
source "${LIB_DIR}/update-track.sh"
# shellcheck source=lib/install-common.sh
source "${LIB_DIR}/install-common.sh"
_brokerai_ensure_git_safe_directory "${INSTALL_DIR}"

if [[ "${BROKERAI_AUTO_UPDATE}" != "true" && "${FORCE}" != "true" ]]; then
  log "Auto-update disabled (BROKERAI_AUTO_UPDATE=${BROKERAI_AUTO_UPDATE}), skipping"
  exit 0
fi

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  log "No git repository at ${INSTALL_DIR}, skipping"
  exit 0
fi

cd "${INSTALL_DIR}"

CURRENT="$(_brokerai_git_head 2>/dev/null || echo unknown)"
_brokerai_read_version_lock

log "Checking for updates (track=${BROKERAI_UPDATE_TRACK}, current=${CURRENT})"

if ! _brokerai_resolve_update_target 2>>"${LOG_FILE}"; then
  log "ERROR: failed to resolve update target"
  exit 1
fi

log "Target: ${BROKERAI_TARGET_DISPLAY} @ ${BROKERAI_TARGET_COMMIT:0:7}"

COMMIT_RELATION="$(_brokerai_commit_relation "${CURRENT}" "${BROKERAI_TARGET_COMMIT}")"
case "${COMMIT_RELATION}" in
  same)
    log "Already up to date (${BROKERAI_TARGET_DISPLAY} @ ${BROKERAI_TARGET_COMMIT:0:7})"
    exit 0
    ;;
  downgrade)
    log "Refusing downgrade: installed ${CURRENT:0:7} is ahead of target ${BROKERAI_TARGET_COMMIT:0:7} (${BROKERAI_TARGET_DISPLAY})"
    exit 0
    ;;
  unknown)
    log "ERROR: could not compare installed ${CURRENT:0:7} with target ${BROKERAI_TARGET_COMMIT:0:7}"
    exit 1
    ;;
esac

log "Updating ${CURRENT:0:7} -> ${BROKERAI_TARGET_COMMIT:0:7} (${BROKERAI_TARGET_DISPLAY})"
_brokerai_checkout_target 2>>"${LOG_FILE}"

"${INSTALL_DIR}/venv/bin/pip" install -r requirements.txt -q 2>>"${LOG_FILE}"
"${INSTALL_DIR}/venv/bin/pip" install -e . -q 2>>"${LOG_FILE}"

if [[ -x "${INSTALL_DIR}/scripts/build-frontend.sh" ]] && command -v npm &>/dev/null; then
  "${INSTALL_DIR}/scripts/build-frontend.sh" >>"${LOG_FILE}" 2>&1 || log "WARN: frontend build failed"
fi

chmod +x "${INSTALL_DIR}/scripts/auto-update.sh"
chmod +x "${INSTALL_DIR}/scripts/update-now.sh"
chmod +x "${INSTALL_DIR}/scripts/check-update.sh"
chmod +x "${INSTALL_DIR}/scripts/provision-admin-user.sh" 2>/dev/null || true
ln -sf "${INSTALL_DIR}/scripts/check-update.sh" /usr/local/bin/brokerai-check-update
ln -sf "${INSTALL_DIR}/venv/bin/brokerai" /usr/local/bin/brokerai
_brokerai_install_container_update_command

cp "${INSTALL_DIR}/systemd/brokerai-orchestrator.service" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/brokerai-web.service" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/brokerai-update.service" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/brokerai-update.timer" /etc/systemd/system/
cp "${INSTALL_DIR}/config/sudoers/brokerai-update" /etc/sudoers.d/brokerai-update
cp "${INSTALL_DIR}/config/sudoers/brokerai-admin" /etc/sudoers.d/brokerai-admin
cp "${INSTALL_DIR}/config/sudoers/brokerai-power" /etc/sudoers.d/brokerai-power
chmod 440 /etc/sudoers.d/brokerai-update /etc/sudoers.d/brokerai-admin /etc/sudoers.d/brokerai-power
visudo -cf /etc/sudoers.d/brokerai-update 2>>"${LOG_FILE}" || true
visudo -cf /etc/sudoers.d/brokerai-admin 2>>"${LOG_FILE}" || true
visudo -cf /etc/sudoers.d/brokerai-power 2>>"${LOG_FILE}" || true

chown -R brokerai:brokerai "${INSTALL_DIR}" "${LOG_DIR}" /var/lib/brokerai/data 2>/dev/null || true

systemctl daemon-reload

if [[ "${BROKERAI_AUTO_UPDATE}" == "true" ]]; then
  systemctl enable -q brokerai-update.timer
  systemctl start brokerai-update.timer 2>/dev/null || true
fi

systemctl restart brokerai-orchestrator brokerai-web

NEW="$(_brokerai_git_head)"
_brokerai_write_version_lock "${BROKERAI_TARGET_TRACK}" "${BROKERAI_TARGET_REF}" "${NEW}"
log "Updated to ${BROKERAI_TARGET_DISPLAY} @ ${NEW:0:7} and restarted services"
