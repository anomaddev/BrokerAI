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
  elif [[ "${track}" == "next-major" ]]; then
    ref="${BROKERAI_TARGET_REF:-next-major}"
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

_brokerai_pick_newest_tag_in_major() {
  local py="${1:?}" major="${2:?}" json="${3:-}"
  [[ -n "${json}" ]] || return 1
  local tag
  tag="$(printf '%s' "${json}" | _brokerai_python_read_json "${py}" "
import re
major = int('${major}')
names = []
if isinstance(data, list):
    for item in data:
        if isinstance(item, dict):
            name = item.get('tag_name') or item.get('name') or ''
            if name:
                names.append(name)
if not names:
    sys.exit(1)
def parse_parts(name):
    normalized = re.sub(r'^v', '', name)
    parts = [int(x) for x in re.findall(r'\\d+', normalized)]
    return parts
candidates = []
for name in names:
    parts = parse_parts(name)
    if parts and parts[0] == major:
        candidates.append((parts, name))
if not candidates:
    sys.exit(1)
candidates.sort(key=lambda item: item[0], reverse=True)
print(candidates[0][1])
")"
  [[ -n "${tag}" ]] || return 1
  echo "${tag}"
}

_brokerai_semver_major() {
  local ref="${1:-}" py major
  [[ -n "${ref}" ]] || return 1
  py="${BROKERAI_PYTHON:-${INSTALL_DIR}/venv/bin/python}"
  if [[ ! -x "${py}" ]]; then
    py="$(command -v python3 || true)"
  fi
  [[ -n "${py}" ]] || return 1
  major="$(
    REF="${ref}" "${py}" -c '
import os, re
ref = os.environ.get("REF", "")
normalized = re.sub(r"^v", "", ref.strip())
parts = [int(x) for x in re.findall(r"\d+", normalized)]
if not parts:
    raise SystemExit(1)
print(parts[0])
' 2>/dev/null || true
  )"
  [[ -n "${major}" ]] || return 1
  echo "${major}"
}

_brokerai_installed_semver_ref() {
  local ref="${BROKERAI_LOCK_REF:-}" tag
  if [[ -n "${ref}" && "${ref}" != "latest" && "${ref}" != "main" && "${ref}" =~ [0-9] ]]; then
    _brokerai_normalize_tag "${ref}"
    return 0
  fi
  tag="$(_brokerai_git describe --tags --exact-match 2>/dev/null || true)"
  if [[ -n "${tag}" ]]; then
    _brokerai_normalize_tag "${tag}"
    return 0
  fi
  tag="$(_brokerai_git tag --points-at HEAD 2>/dev/null | head -1 || true)"
  if [[ -n "${tag}" ]]; then
    _brokerai_normalize_tag "${tag}"
    return 0
  fi
  echo "Could not determine installed semver version for next-major track. Install from a release tag first." >&2
  return 1
}

_brokerai_github_release_tags_json() {
  local repo_slug="${1:?}" py="${2:?}"
  local releases_json tags_json
  releases_json="$(_brokerai_github_api_get "https://api.github.com/repos/${repo_slug}/releases?per_page=100")"
  tags_json="$(_brokerai_github_api_get "https://api.github.com/repos/${repo_slug}/tags?per_page=100")"
  COMBINED_RELEASES="${releases_json}" COMBINED_TAGS="${tags_json}" "${py}" -c '
import json, os
items = []
for raw in (os.environ.get("COMBINED_RELEASES", ""), os.environ.get("COMBINED_TAGS", "")):
    if not raw:
        continue
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if isinstance(data, list):
        items.extend(data)
print(json.dumps(items))
' 2>/dev/null || true
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

_brokerai_github_next_major_release_tag() {
  local repo_slug installed_ref major py tags_json tag
  repo_slug="$(_brokerai_parse_repo_slug "${BROKERAI_REPO}")"
  py="${BROKERAI_PYTHON:-${INSTALL_DIR}/venv/bin/python}"
  if [[ ! -x "${py}" ]]; then
    py="$(command -v python3 || true)"
  fi
  [[ -n "${py}" ]] || {
    echo "python3 is required to resolve next-major release tags" >&2
    return 1
  }

  installed_ref="$(_brokerai_installed_semver_ref)" || return 1
  major="$(_brokerai_semver_major "${installed_ref}")" || {
    echo "Could not parse semver major from installed version ${installed_ref}" >&2
    return 1
  }

  tags_json="$(_brokerai_github_release_tags_json "${repo_slug}" "${py}")"
  tag="$(_brokerai_pick_newest_tag_in_major "${py}" "${major}" "${tags_json}")" || {
    tag="$(_brokerai_git_latest_remote_tag)" || true
    if [[ -n "${tag}" ]]; then
      local remote_major
      remote_major="$(_brokerai_semver_major "$(_brokerai_normalize_tag "${tag}")")" || true
      if [[ "${remote_major}" != "${major}" ]]; then
        tag=""
      fi
    fi
  }

  if [[ -z "${tag}" ]]; then
    echo "No GitHub releases or tags found for major version ${major} on ${repo_slug}." >&2
    return 1
  fi

  echo "${tag}"
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
    next-major)
      local next_major_tag installed_major
      next_major_tag="$(_brokerai_github_next_major_release_tag)" || return 1
      if [[ -z "${next_major_tag}" ]]; then
        echo "Could not resolve next-major GitHub release" >&2
        return 1
      fi
      installed_major="$(_brokerai_semver_major "$(_brokerai_installed_semver_ref)")" || return 1
      BROKERAI_TARGET_REF="$(_brokerai_normalize_tag "${next_major_tag}")"
      local resolved_next_tag
      resolved_next_tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")" || return 1
      BROKERAI_TARGET_COMMIT="$(_brokerai_git rev-parse "${resolved_next_tag}^{commit}")"
      BROKERAI_TARGET_DISPLAY="next-major:${installed_major}.x→${BROKERAI_TARGET_REF}"
      ;;
    *)
      echo "Unknown BROKERAI_UPDATE_TRACK: ${BROKERAI_UPDATE_TRACK}" >&2
      return 1
      ;;
  esac
}

_brokerai_commit_exists() {
  local sha="$1"
  [[ -n "${sha}" && "${sha}" != "unknown" ]] || return 1
  _brokerai_git cat-file -e "${sha}^{commit}" 2>/dev/null
}

_brokerai_commit_relation_once() {
  local installed="$1" target="$2"
  if [[ "${installed}" == "${target}" ]]; then
    echo "same"
    return 0
  fi
  if _brokerai_git merge-base --is-ancestor "${installed}" "${target}" 2>/dev/null; then
    echo "upgrade"
    return 0
  fi
  if _brokerai_git merge-base --is-ancestor "${target}" "${installed}" 2>/dev/null; then
    echo "downgrade"
    return 0
  fi
  echo "diverged"
}

_brokerai_deepen_commit_history() {
  local installed="$1" target="$2"
  _brokerai_git fetch origin "${installed}" "${target}" --depth=50 2>/dev/null \
    || _brokerai_git fetch origin --depth=100 2>/dev/null \
    || _brokerai_git fetch --unshallow 2>/dev/null \
    || true
}

_brokerai_commit_relation() {
  local installed="$1" target="$2" relation
  BROKERAI_COMMIT_RELATION=""

  if [[ -z "${installed}" || -z "${target}" || "${installed}" == "unknown" || "${target}" == "unknown" ]]; then
    BROKERAI_COMMIT_RELATION="unknown"
    echo "unknown"
    return 0
  fi

  if ! _brokerai_commit_exists "${installed}" || ! _brokerai_commit_exists "${target}"; then
    _brokerai_deepen_commit_history "${installed}" "${target}"
  fi

  relation="$(_brokerai_commit_relation_once "${installed}" "${target}")"

  if ! _brokerai_commit_exists "${installed}" || ! _brokerai_commit_exists "${target}"; then
    BROKERAI_COMMIT_RELATION="unknown"
    echo "unknown"
    return 0
  fi

  if [[ "${relation}" == "diverged" ]]; then
    _brokerai_deepen_commit_history "${installed}" "${target}"
    relation="$(_brokerai_commit_relation_once "${installed}" "${target}")"
  fi

  BROKERAI_COMMIT_RELATION="${relation}"
  echo "${relation}"
}

_brokerai_checkout_target() {
  case "${BROKERAI_UPDATE_TRACK}" in
    branch)
      _brokerai_git checkout "${BROKERAI_BRANCH}" 2>/dev/null \
        || _brokerai_git checkout -B "${BROKERAI_BRANCH}" "origin/${BROKERAI_BRANCH}"
      _brokerai_git reset --hard "origin/${BROKERAI_BRANCH}"
      ;;
    release | latest-release | next-major)
      local tag
      tag="$(_brokerai_resolve_release_tag "${BROKERAI_TARGET_REF}")"
      _brokerai_git checkout --detach "${tag}"
      ;;
  esac
}
