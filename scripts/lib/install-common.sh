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

_brokerai_upsert_config_kv() {
  local config_file="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "${config_file}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${config_file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >>"${config_file}"
  fi
}

# Apply public Supabase URL knobs when BROKERAI_SUPABASE_DOMAIN is set.
# Updates deploy/supabase/.env and optionally recreates the auth container.
_brokerai_apply_supabase_public_urls() {
  local install_dir="${1:-/opt/brokerai}"
  local broker_domain="${2:-}"
  local supabase_domain="${3:-}"
  local recreate_auth="${4:-1}"
  local supabase_env="${install_dir}/deploy/supabase/.env"

  if [[ -z "${supabase_domain}" ]]; then
    return 0
  fi
  if [[ ! -f "${supabase_env}" ]]; then
    echo "Supabase .env missing at ${supabase_env} — skip public URL apply" >&2
    return 0
  fi

  local public_url="https://${supabase_domain}"
  local site_url="http://127.0.0.1:5173"
  if [[ -n "${broker_domain}" ]]; then
    site_url="https://${broker_domain}"
  fi

  python3 - "${supabase_env}" "${public_url}" "${site_url}" "${supabase_domain}" <<'PY'
import sys
from pathlib import Path

p = Path(sys.argv[1])
public_url, site_url, proxy_domain = sys.argv[2], sys.argv[3], sys.argv[4]
replacements = {
    "SUPABASE_PUBLIC_URL": public_url,
    "API_EXTERNAL_URL": public_url,
    "SITE_URL": site_url,
    "ADDITIONAL_REDIRECT_URLS": f"{site_url}/**",
    "PROXY_DOMAIN": proxy_domain,
}
lines = []
seen: set[str] = set()
for line in p.read_text().splitlines():
    if not line or line.lstrip().startswith("#") or "=" not in line:
        lines.append(line)
        continue
    key, _, _val = line.partition("=")
    key = key.strip()
    if key in replacements:
        lines.append(f"{key}={replacements[key]}")
        seen.add(key)
    else:
        lines.append(line)
for key, val in replacements.items():
    if key not in seen:
        lines.append(f"{key}={val}")
p.write_text("\n".join(lines) + "\n")
PY

  if [[ "${recreate_auth}" == "1" ]] && command -v docker >/dev/null 2>&1; then
    (
      cd "${install_dir}/deploy/supabase"
      docker compose -f docker-compose.yml -f docker-compose.brokerai.yml up -d --force-recreate auth 2>/dev/null \
        || docker compose -f docker-compose.yml -f docker-compose.brokerai.yml up -d --force-recreate 2>/dev/null \
        || true
    )
  fi
}

# Optional host Caddy TLS when BROKERAI_DOMAIN is set. Leaves plain HTTP on
# :1989 when unset. Optional BROKERAI_SUPABASE_DOMAIN exposes Kong/Studio on a
# second hostname (still bound to 127.0.0.1 in compose; Caddy is the edge).
_brokerai_maybe_install_caddy_tls() {
  local install_dir="${1:-/opt/brokerai}"
  local config_file="${2:-/etc/brokerai/config.env}"
  local domain="${BROKERAI_DOMAIN:-}"
  local supabase_domain="${BROKERAI_SUPABASE_DOMAIN:-}"

  if [[ -z "${domain}" && -f "${config_file}" ]]; then
    domain="$(grep -E '^BROKERAI_DOMAIN=' "${config_file}" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  if [[ -z "${supabase_domain}" && -f "${config_file}" ]]; then
    supabase_domain="$(grep -E '^BROKERAI_SUPABASE_DOMAIN=' "${config_file}" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  domain="${domain//[$'\r\n']/}"
  supabase_domain="${supabase_domain//[$'\r\n']/}"
  if [[ -z "${domain}" ]]; then
    echo "BROKERAI_DOMAIN unset — skipping Caddy TLS (HTTP on :1989)"
    return 0
  fi

  export BROKERAI_DOMAIN="${domain}"
  export BROKERAI_INSTALL_DIR="${install_dir}"
  if [[ -n "${supabase_domain}" ]]; then
    export BROKERAI_SUPABASE_DOMAIN="${supabase_domain}"
  fi
  if [[ -f "${config_file}" ]]; then
    local web_port
    web_port="$(grep -E '^BROKERAI_WEB_PORT=' "${config_file}" 2>/dev/null | head -1 | cut -d= -f2- || true)"
    if [[ -n "${web_port}" ]]; then
      export BROKERAI_WEB_PORT="${web_port}"
    fi
  fi

  chmod +x "${install_dir}/scripts/lib/install-caddy.sh"
  bash "${install_dir}/scripts/lib/install-caddy.sh"

  _brokerai_upsert_config_kv "${config_file}" "BROKERAI_DOMAIN" "${domain}"
  _brokerai_upsert_config_kv "${config_file}" "BROKERAI_WEB_BIND" "127.0.0.1"
  _brokerai_upsert_config_kv "${config_file}" "BROKERAI_SESSION_COOKIE_SECURE" "true"

  if [[ -n "${supabase_domain}" ]]; then
    _brokerai_upsert_config_kv "${config_file}" "BROKERAI_SUPABASE_DOMAIN" "${supabase_domain}"
    _brokerai_upsert_config_kv "${config_file}" "BROKERAI_SUPABASE_URL" "https://${supabase_domain}"
    _brokerai_apply_supabase_public_urls "${install_dir}" "${domain}" "${supabase_domain}" "1"
  fi
}

_brokerai_install_postgres_backup() {
  local install_dir="${1:-/opt/brokerai}"
  local config_file="${2:-/etc/brokerai/config.env}"
  local backup_dir="${BROKERAI_BACKUP_DIR:-/var/lib/brokerai/backups/postgres}"

  mkdir -p "${backup_dir}"
  chmod 750 "${backup_dir}"
  chown root:brokerai "${backup_dir}" 2>/dev/null || true

  chmod +x "${install_dir}/scripts/backup-postgres.sh"
  cp "${install_dir}/systemd/brokerai-postgres-backup.service" /etc/systemd/system/
  cp "${install_dir}/systemd/brokerai-postgres-backup.timer" /etc/systemd/system/

  if [[ -f "${config_file}" ]]; then
    if ! grep -q '^BROKERAI_BACKUP_DIR=' "${config_file}" 2>/dev/null; then
      {
        echo ""
        echo "# Postgres logical dumps (systemd timer brokerai-postgres-backup.timer)"
        echo "BROKERAI_BACKUP_DIR=${backup_dir}"
        echo "BROKERAI_BACKUP_RETENTION_DAYS=${BROKERAI_BACKUP_RETENTION_DAYS:-7}"
      } >>"${config_file}"
    fi
  fi

  systemctl daemon-reload
  systemctl enable --now brokerai-postgres-backup.timer
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
