#!/usr/bin/env bash
# Shared helpers for BrokerAI update track resolution.
# Sourced by auto-update.sh — do not run directly.

_brokerai_parse_repo_slug() {
  local url="${1:-}"
  url="${url%.git}"
  url="${url#https://github.com/}"
  url="${url#http://github.com/}"
  echo "${url}"
}

_brokerai_normalize_tag() {
  local tag="${1#v}"
  echo "${tag}"
}

_brokerai_read_version_lock() {
  BROKERAI_LOCK_TRACK=""
  BROKERAI_LOCK_REF=""
  BROKERAI_LOCK_COMMIT=""
  if [[ ! -f "${VERSION_FILE}" ]]; then
    return 0
  fi
  if grep -q '=' "${VERSION_FILE}"; then
    # shellcheck source=/dev/null
    source "${VERSION_FILE}"
    BROKERAI_LOCK_TRACK="${track:-}"
    BROKERAI_LOCK_REF="${ref:-}"
    BROKERAI_LOCK_COMMIT="${commit:-}"
  else
    BROKERAI_LOCK_COMMIT="$(tr -d '[:space:]' <"${VERSION_FILE}")"
  fi
}

_brokerai_write_version_lock() {
  local track="$1" ref="$2" commit="$3"
  cat >"${VERSION_FILE}" <<EOF
track=${track}
ref=${ref}
commit=${commit}
EOF
}

_brokerai_write_install_lock_from_config() {
  local commit="$1"
  local track="${BROKERAI_UPDATE_TRACK:-branch}"
  local ref="${BROKERAI_BRANCH:-main}"
  if [[ "${track}" == "release" && -n "${BROKERAI_RELEASE:-}" ]]; then
    ref="$(_brokerai_normalize_tag "${BROKERAI_RELEASE}")"
  elif [[ "${track}" == "latest-release" ]]; then
    ref="latest"
  fi
  _brokerai_write_version_lock "${track}" "${ref}" "${commit}"
}

_brokerai_github_latest_release_tag() {
  local repo_slug latest_json py
  repo_slug="$(_brokerai_parse_repo_slug "${BROKERAI_REPO}")"
  latest_json="$(curl -fsSL "https://api.github.com/repos/${repo_slug}/releases/latest")"
  py="${BROKERAI_PYTHON:-${INSTALL_DIR}/venv/bin/python}"
  if [[ ! -x "${py}" ]]; then
    py="$(command -v python3 || true)"
  fi
  echo "${latest_json}" | "${py}" -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('tag_name', ''))
"
}

_brokerai_resolve_release_tag() {
  local requested normalized tag
  requested="$1"
  normalized="$(_brokerai_normalize_tag "${requested}")"

  git fetch origin "refs/tags/v${normalized}:refs/tags/v${normalized}" --depth=1 2>/dev/null \
    || git fetch origin "refs/tags/${normalized}:refs/tags/${normalized}" --depth=1 2>/dev/null \
    || git fetch origin --tags --depth=1 2>/dev/null \
    || true

  if git rev-parse "v${normalized}" >/dev/null 2>&1; then
    tag="v${normalized}"
  elif git rev-parse "${normalized}" >/dev/null 2>&1; then
    tag="${normalized}"
  elif git rev-parse "refs/tags/v${normalized}" >/dev/null 2>&1; then
    tag="v${normalized}"
  elif git rev-parse "refs/tags/${normalized}" >/dev/null 2>&1; then
    tag="${normalized}"
  else
    echo ""
    return 1
  fi
  echo "${tag}"
}

_brokerai_resolve_update_target() {
  BROKERAI_TARGET_TRACK="${BROKERAI_UPDATE_TRACK}"
  BROKERAI_TARGET_REF=""
  BROKERAI_TARGET_COMMIT=""
  BROKERAI_TARGET_DISPLAY=""

  case "${BROKERAI_UPDATE_TRACK}" in
    branch)
      BROKERAI_TARGET_REF="${BROKERAI_BRANCH}"
      if ! git fetch origin "${BROKERAI_BRANCH}" --depth=1 2>/dev/null; then
        return 1
      fi
      BROKERAI_TARGET_COMMIT="$(git rev-parse "origin/${BROKERAI_BRANCH}")"
      BROKERAI_TARGET_DISPLAY="branch:${BROKERAI_BRANCH}"
      ;;
    release)
      if [[ -z "${BROKERAI_RELEASE}" ]]; then
        echo "BROKERAI_RELEASE is required when BROKERAI_UPDATE_TRACK=release" >&2
        return 1
      fi
      BROKERAI_TARGET_REF="$(_brokerai_normalize_tag "${BROKERAI_RELEASE}")"
      local tag
      tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")" || return 1
      BROKERAI_TARGET_COMMIT="$(git rev-parse "${tag}^{commit}")"
      BROKERAI_TARGET_DISPLAY="release:${BROKERAI_TARGET_REF}"
      ;;
    latest-release)
      local latest_tag
      latest_tag="$(_brokerai_github_latest_release_tag)" || return 1
      if [[ -z "${latest_tag}" ]]; then
        echo "Could not resolve latest GitHub release" >&2
        return 1
      fi
      BROKERAI_TARGET_REF="$(_brokerai_normalize_tag "${latest_tag}")"
      local resolved_tag
      resolved_tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")" || return 1
      BROKERAI_TARGET_COMMIT="$(git rev-parse "${resolved_tag}^{commit}")"
      BROKERAI_TARGET_DISPLAY="latest-release:${BROKERAI_TARGET_REF}"
      ;;
    *)
      echo "Unknown BROKERAI_UPDATE_TRACK: ${BROKERAI_UPDATE_TRACK}" >&2
      return 1
      ;;
  esac
}

_brokerai_checkout_target() {
  case "${BROKERAI_UPDATE_TRACK}" in
    branch)
      git checkout "${BROKERAI_BRANCH}" 2>/dev/null || git checkout -B "${BROKERAI_BRANCH}" "origin/${BROKERAI_BRANCH}"
      git reset --hard "origin/${BROKERAI_BRANCH}"
      ;;
    release | latest-release)
      local tag
      tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")"
      git checkout --detach "${tag}"
      ;;
  esac
}
