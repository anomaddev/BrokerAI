#!/usr/bin/env bash
# Copyright (c) 2021-2026 anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI
#
# Check whether a BrokerAI update is available (read-only — does not apply).
#
# Usage:
#   brokerai-check-update
#   /opt/brokerai/scripts/check-update.sh
#   /opt/brokerai/scripts/check-update.sh --json
#
# Exit codes:
#   0 — up to date
#   1 — update available
#   2 — error

set -euo pipefail

APP="BrokerAI"

_resolve_script_dir() {
  local source="${BASH_SOURCE[0]}"
  while [[ -L "${source}" ]]; do
    local dir
    dir="$(cd -P "$(dirname "${source}")" && pwd)"
    source="$(readlink "${source}")"
    [[ "${source}" != /* ]] && source="${dir}/${source}"
  done
  cd -P "$(dirname "${source}")" && pwd
}

SCRIPT_DIR="$(_resolve_script_dir)"
INSTALL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="/etc/brokerai/config.env"
VERSION_FILE="${VERSION_FILE:-/opt/${APP}_version.txt}"
LIB_DIR="${SCRIPT_DIR}/lib"

JSON=false
QUIET=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Check for BrokerAI updates without installing them.

Options:
  --json    Output machine-readable JSON
  --quiet   Only print when an update is available (or on error)
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=true; shift ;;
    --quiet) QUIET=true; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

_CALLER_UPDATE_TRACK="${BROKERAI_UPDATE_TRACK:-}"
_CALLER_BRANCH="${BROKERAI_BRANCH:-}"
_CALLER_RELEASE="${BROKERAI_RELEASE:-}"
_CALLER_REPO="${BROKERAI_REPO:-}"
_CALLER_VERSION_FILE="${VERSION_FILE:-}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck source=/dev/null
  set -a
  source "${CONFIG_FILE}"
  set +a
elif [[ -f "${INSTALL_DIR}/.env" ]]; then
  # shellcheck source=/dev/null
  set -a
  source "${INSTALL_DIR}/.env"
  set +a
fi

if [[ -n "${_CALLER_UPDATE_TRACK}" ]]; then BROKERAI_UPDATE_TRACK="${_CALLER_UPDATE_TRACK}"; fi
if [[ -n "${_CALLER_BRANCH}" ]]; then BROKERAI_BRANCH="${_CALLER_BRANCH}"; fi
if [[ -n "${_CALLER_RELEASE}" ]]; then BROKERAI_RELEASE="${_CALLER_RELEASE}"; fi
if [[ -n "${_CALLER_REPO}" ]]; then BROKERAI_REPO="${_CALLER_REPO}"; fi
if [[ -n "${_CALLER_VERSION_FILE}" ]]; then VERSION_FILE="${_CALLER_VERSION_FILE}"; fi

BROKERAI_REPO="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
BROKERAI_UPDATE_TRACK="${BROKERAI_UPDATE_TRACK:-branch}"
BROKERAI_BRANCH="${BROKERAI_BRANCH:-main}"
BROKERAI_RELEASE="${BROKERAI_RELEASE:-}"
BROKERAI_PYTHON="${INSTALL_DIR}/venv/bin/python"
if [[ ! -x "${BROKERAI_PYTHON}" ]]; then
  BROKERAI_PYTHON="$(command -v python3 || true)"
fi

# shellcheck source=lib/update-track.sh
source "${LIB_DIR}/update-track.sh"

if [[ $EUID -eq 0 ]]; then
  _brokerai_ensure_git_safe_directory "${INSTALL_DIR}"
fi

fail() {
  if [[ "${JSON}" == "true" ]]; then
    export _FAIL_MSG="$1"
    "${BROKERAI_PYTHON}" -c 'import json, os; print(json.dumps({"status": "error", "message": os.environ.get("_FAIL_MSG", "Unknown error")}))'
  elif [[ "${QUIET}" != "true" ]]; then
    echo "Error: $1" >&2
  else
    echo "Error: $1" >&2
  fi
  exit 2
}

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  fail "No git repository at ${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

CURRENT="$(_brokerai_git_head 2>/dev/null || echo unknown)"
_brokerai_read_version_lock

_RESOLVE_ERR_FILE="$(mktemp "${TMPDIR:-/tmp}/brokerai-resolve.XXXXXX")"
if ! _brokerai_resolve_update_target 2>"${_RESOLVE_ERR_FILE}"; then
  RESOLVE_MSG="$(tr -d '\n' <"${_RESOLVE_ERR_FILE}" | sed 's/  */ /g')"
  rm -f "${_RESOLVE_ERR_FILE}"
  if [[ -z "${RESOLVE_MSG}" ]]; then
    RESOLVE_MSG="Failed to resolve update target (track=${BROKERAI_UPDATE_TRACK})"
  fi
  fail "${RESOLVE_MSG}"
fi
rm -f "${_RESOLVE_ERR_FILE}"

UPDATE_AVAILABLE=false
if [[ "${CURRENT}" != "${BROKERAI_TARGET_COMMIT}" \
  || "${BROKERAI_LOCK_TRACK}" != "${BROKERAI_TARGET_TRACK}" \
  || "${BROKERAI_LOCK_REF}" != "${BROKERAI_TARGET_REF}" ]]; then
  UPDATE_AVAILABLE=true
fi

if [[ "${JSON}" == "true" ]]; then
  export _CHK_STATUS _CHK_DISPLAY _CHK_TRACK _CHK_LOCK_TRACK _CHK_LOCK_REF
  export _CHK_CURRENT _CHK_TARGET_TRACK _CHK_TARGET_REF _CHK_TARGET_COMMIT _CHK_AVAILABLE
  if [[ "${UPDATE_AVAILABLE}" == "true" ]]; then
    _CHK_STATUS="update-available"
  else
    _CHK_STATUS="up-to-date"
  fi
  _CHK_DISPLAY="${BROKERAI_TARGET_DISPLAY}"
  _CHK_TRACK="${BROKERAI_UPDATE_TRACK}"
  _CHK_LOCK_TRACK="${BROKERAI_LOCK_TRACK}"
  _CHK_LOCK_REF="${BROKERAI_LOCK_REF}"
  _CHK_CURRENT="${CURRENT}"
  _CHK_TARGET_TRACK="${BROKERAI_TARGET_TRACK}"
  _CHK_TARGET_REF="${BROKERAI_TARGET_REF}"
  _CHK_TARGET_COMMIT="${BROKERAI_TARGET_COMMIT}"
  _CHK_AVAILABLE="${UPDATE_AVAILABLE}"
  "${BROKERAI_PYTHON}" <<'PY'
import json, os
current = os.environ["_CHK_CURRENT"]
target = os.environ["_CHK_TARGET_COMMIT"]
print(json.dumps({
    "status": os.environ["_CHK_STATUS"],
    "configured_pin": os.environ["_CHK_DISPLAY"],
    "update_track": os.environ["_CHK_TRACK"],
    "installed": {
        "track": os.environ["_CHK_LOCK_TRACK"],
        "ref": os.environ["_CHK_LOCK_REF"],
        "commit": current,
        "commit_short": current[:7],
    },
    "available": {
        "track": os.environ["_CHK_TARGET_TRACK"],
        "ref": os.environ["_CHK_TARGET_REF"],
        "commit": target,
        "commit_short": target[:7],
    },
}))
PY
elif [[ "${UPDATE_AVAILABLE}" == "true" ]]; then
  echo "Update available"
  echo "  Configured : ${BROKERAI_TARGET_DISPLAY}"
  echo "  Installed  : ${BROKERAI_LOCK_TRACK:-?}:${BROKERAI_LOCK_REF:-?} @ ${CURRENT:0:7}"
  echo "  Available  : ${BROKERAI_TARGET_DISPLAY} @ ${BROKERAI_TARGET_COMMIT:0:7}"
  echo ""
  echo "Apply with: sudo /opt/brokerai/scripts/update-now.sh"
elif [[ "${QUIET}" != "true" ]]; then
  echo "Up to date"
  echo "  Pin        : ${BROKERAI_TARGET_DISPLAY}"
  echo "  Commit     : ${CURRENT:0:7}"
fi

if [[ "${UPDATE_AVAILABLE}" == "true" ]]; then
  exit 1
fi
exit 0
