#!/usr/bin/env bash
# Shared helpers for BrokerAI production installs (Proxmox LXC + standalone).
# Sourced by install scripts — do not run directly.

_brokerai_require_python311() {
  if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "Python 3.11+ is required (found: $(python3 --version 2>/dev/null || echo unknown))" >&2
    return 1
  fi
}

_brokerai_raw_github_url() {
  local repo="${1:-https://github.com/anomaddev/BrokerAI}"
  local branch="${2:-main}"
  local slug="${repo#https://github.com/}"
  slug="${slug#http://github.com/}"
  slug="${slug%.git}"
  printf 'https://raw.githubusercontent.com/%s/%s' "${slug}" "${branch}"
}

_brokerai_seed_production_config() {
  local config_dir="${1:-/etc/brokerai}"
  local example="${2:-/opt/brokerai/config/config.env.example}"
  local data_dir="${3:-/var/lib/brokerai/data}"
  local log_dir="${4:-/var/log/brokerai}"
  local config_file="${config_dir}/config.env"

  if [[ -f "${config_file}" ]]; then
    return 0
  fi

  cp "${example}" "${config_file}"
  local secret_key
  secret_key="$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c32)"
  sed -i "s|^BROKERAI_SECRET_KEY=.*|BROKERAI_SECRET_KEY=${secret_key}|" "${config_file}"
  {
    echo ""
    echo "# Production paths"
    echo "BROKERAI_DATA_DIR=${data_dir}"
    echo "BROKERAI_LOG_DIR=${log_dir}"
  } >>"${config_file}"
}

# community-scripts install.func points /usr/bin/update at ProxmoxVE ct/<app>.sh,
# which does not exist for BrokerAI. Use this repo's ct/brokerai.sh instead.
_brokerai_install_container_update_command() {
  local repo="${BROKERAI_REPO:-https://github.com/anomaddev/BrokerAI}"
  local branch="${BROKERAI_BRANCH:-main}"
  local ct_url="$(_brokerai_raw_github_url "${repo}" "${branch}")/ct/brokerai.sh"

  cat > /usr/bin/update <<EOF
#!/bin/bash
set -a
[ -f /etc/profile.d/90-http-proxy.sh ] && . /etc/profile.d/90-http-proxy.sh
set +a
bash -c "\$(curl -fsSL '${ct_url}')"
EOF
  chmod +x /usr/bin/update
}
