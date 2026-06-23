#!/usr/bin/env bash
# Shared helpers for BrokerAI update track resolution.
# Sourced by auto-update.sh — do not run directly.

BROKERAI_INSTALL_DIR="${BROKERAI_INSTALL_DIR:-${INSTALL_DIR:-/opt/brokerai}}"

_brokerai_git() {
  git -c "safe.directory=${BROKERAI_INSTALL_DIR}" -C "${BROKERAI_INSTALL_DIR}" "$@"
}

_brokerai_git_head() {
  _brokerai_git rev-parse HEAD 2>/dev/null || _brokerai_read_head_commit
}

_brokerai_ensure_git_safe_directory() {
  local dir="${1:-${BROKERAI_INSTALL_DIR}}"
  if git config --system --get-all safe.directory 2>/dev/null | grep -Fxq "${dir}"; then
    return 0
  fi
  if git config --global --get-all safe.directory 2>/dev/null | grep -Fxq "${dir}"; then
    return 0
  fi
  git config --system --add safe.directory "${dir}" 2>/dev/null \
    || git config --global --add safe.directory "${dir}" 2>/dev/null \
    || printf '[safe]\n\tdirectory = %s\n' "${dir}" >>/etc/gitconfig
}

_brokerai_read_head_commit() {
  local ref head_file git_dir="${BROKERAI_INSTALL_DIR}/.git"
  head_file="${git_dir}/HEAD"
  [[ -f "${head_file}" ]] || return 1
  ref="$(<"${head_file}")"
  ref="${ref#ref: }"
  if [[ -f "${git_dir}/${ref}" ]]; then
    tr -d '[:space:]' <"${git_dir}/${ref}"
    return 0
  fi
  if [[ -f "${git_dir}/packed-refs" ]]; then
    awk -v r="${ref}" '$2 == r { print $1; exit }' "${git_dir}/packed-refs"
    return 0
  fi
  return 1
}

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

_brokerai_github_api_get() {
  curl -fsSL \
    -H "Accept: application/vnd.github+json" \
    -H "User-Agent: BrokerAI-update-check" \
    "$1" 2>/dev/null || true
}

_brokerai_python_read_json() {
  local py="${1:?}"
  local expr="${2:?}"
  "${py}" -c "
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
${expr}
" 2>/dev/null || true
}

_brokerai_pick_newest_tag_name() {
  local py="${1:?}"
  local json="${2:-}"
  [[ -n "${json}" ]] || return 1
  local tag
  tag="$(printf '%s' "${json}" | _brokerai_python_read_json "${py}" "
import re
names = []
if isinstance(data, list):
    for item in data:
        if isinstance(item, dict):
            name = item.get('tag_name') or item.get('name') or ''
            if name:
                names.append(name)
if not names:
    sys.exit(1)
def sort_key(name):
    normalized = re.sub(r'^v', '', name)
    parts = [int(x) for x in re.findall(r'\\d+', normalized)]
    return parts or [0]
names.sort(key=sort_key, reverse=True)
print(names[0])
")"
  [[ -n "${tag}" ]] || return 1
  echo "${tag}"
}

_brokerai_git_latest_remote_tag() {
  local tag
  if ! _brokerai_git fetch origin --tags --depth=1 2>/dev/null; then
    _brokerai_git fetch origin --tags 2>/dev/null || true
  fi
  tag="$(_brokerai_git tag -l --sort=-v:refname 2>/dev/null | head -1 || true)"
  [[ -n "${tag}" ]] || return 1
  echo "${tag}"
}

_brokerai_github_latest_release_tag() {
  local repo_slug latest_json releases_json tags_json py tag
  repo_slug="$(_brokerai_parse_repo_slug "${BROKERAI_REPO}")"
  py="${BROKERAI_PYTHON:-${INSTALL_DIR}/venv/bin/python}"
  if [[ ! -x "${py}" ]]; then
    py="$(command -v python3 || true)"
  fi
  [[ -n "${py}" ]] || {
    echo "python3 is required to resolve latest release tags" >&2
    return 1
  }

  latest_json="$(_brokerai_github_api_get "https://api.github.com/repos/${repo_slug}/releases/latest")"
  if [[ -n "${latest_json}" ]]; then
    tag="$(printf '%s' "${latest_json}" | _brokerai_python_read_json "${py}" "
tag = data.get('tag_name', '') if isinstance(data, dict) else ''
if not tag:
    sys.exit(1)
print(tag)
")"
    if [[ -n "${tag}" ]]; then
      echo "${tag}"
      return 0
    fi
  fi

  releases_json="$(_brokerai_github_api_get "https://api.github.com/repos/${repo_slug}/releases?per_page=30")"
  tag="$(_brokerai_pick_newest_tag_name "${py}" "${releases_json}")" && {
    echo "${tag}"
    return 0
  }

  tags_json="$(_brokerai_github_api_get "https://api.github.com/repos/${repo_slug}/tags?per_page=100")"
  tag="$(_brokerai_pick_newest_tag_name "${py}" "${tags_json}")" && {
    echo "${tag}"
    return 0
  }

  tag="$(_brokerai_git_latest_remote_tag)" && {
    echo "${tag}"
    return 0
  }

  echo "No GitHub releases or tags found for ${repo_slug}. Publish a release or tag to use latest-release." >&2
  return 1
}

_brokerai_resolve_release_tag() {
  local requested normalized tag
  requested="$1"
  normalized="$(_brokerai_normalize_tag "${requested}")"

  _brokerai_git fetch origin "refs/tags/v${normalized}:refs/tags/v${normalized}" --depth=1 2>/dev/null \
    || _brokerai_git fetch origin "refs/tags/${normalized}:refs/tags/${normalized}" --depth=1 2>/dev/null \
    || _brokerai_git fetch origin --tags --depth=1 2>/dev/null \
    || true

  if _brokerai_git rev-parse "v${normalized}" >/dev/null 2>&1; then
    tag="v${normalized}"
  elif _brokerai_git rev-parse "${normalized}" >/dev/null 2>&1; then
    tag="${normalized}"
  elif _brokerai_git rev-parse "refs/tags/v${normalized}" >/dev/null 2>&1; then
    tag="v${normalized}"
  elif _brokerai_git rev-parse "refs/tags/${normalized}" >/dev/null 2>&1; then
    tag="${normalized}"
  else
    echo ""
    return 1
  fi
  echo "${tag}"
}

_brokerai_acquire_fetch_lock() {
  local lock="${BROKERAI_INSTALL_DIR}/.git/brokerai-update.lock"
  local i
  for i in $(seq 1 30); do
    if mkdir "${lock}" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  echo "Timed out waiting for git update lock" >&2
  return 1
}

_brokerai_release_fetch_lock() {
  rmdir "${BROKERAI_INSTALL_DIR}/.git/brokerai-update.lock" 2>/dev/null || true
}

_brokerai_fetch_branch() {
  local branch="$1"
  local attempt
  if ! _brokerai_acquire_fetch_lock; then
    return 1
  fi
  for attempt in 1 2 3; do
    if _brokerai_git fetch origin "${branch}" --depth=1; then
      _brokerai_release_fetch_lock
      return 0
    fi
    if [[ $attempt -lt 3 ]]; then
      sleep 1
    fi
  done
  _brokerai_release_fetch_lock
  echo "git fetch origin ${branch} failed after 3 attempts" >&2
  return 1
}

_brokerai_resolve_update_target() {
  BROKERAI_TARGET_TRACK="${BROKERAI_UPDATE_TRACK}"
  BROKERAI_TARGET_REF=""
  BROKERAI_TARGET_COMMIT=""
  BROKERAI_TARGET_DISPLAY=""

  case "${BROKERAI_UPDATE_TRACK}" in
    branch)
      BROKERAI_TARGET_REF="${BROKERAI_BRANCH}"
      if ! _brokerai_fetch_branch "${BROKERAI_BRANCH}"; then
        return 1
      fi
      BROKERAI_TARGET_COMMIT="$(_brokerai_git rev-parse "origin/${BROKERAI_BRANCH}")"
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
      BROKERAI_TARGET_COMMIT="$(_brokerai_git rev-parse "${tag}^{commit}")"
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
      BROKERAI_TARGET_COMMIT="$(_brokerai_git rev-parse "${resolved_tag}^{commit}")"
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
      _brokerai_git checkout "${BROKERAI_BRANCH}" 2>/dev/null \
        || _brokerai_git checkout -B "${BROKERAI_BRANCH}" "origin/${BROKERAI_BRANCH}"
      _brokerai_git reset --hard "origin/${BROKERAI_BRANCH}"
      ;;
    release | latest-release)
      local tag
      tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")"
      _brokerai_git checkout --detach "${tag}"
      ;;
  esac
}
