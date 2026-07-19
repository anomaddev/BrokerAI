#!/usr/bin/env bash
# Apply public HTTPS domains via host Caddy (root). Invoked from the web UI with sudo.
#
# Usage:
#   apply-domain-tls.sh --domain broker.example.com
#   apply-domain-tls.sh --domain broker.example.com --supabase-domain supabase.example.com
#   apply-domain-tls.sh --domain broker.example.com --clear-supabase
set -euo pipefail

INSTALL_DIR="${BROKERAI_INSTALL_DIR:-/opt/brokerai}"
CONFIG_FILE="${BROKERAI_CONFIG_FILE:-/etc/brokerai/config.env}"
DOMAIN=""
SUPABASE_DOMAIN=""
CLEAR_SUPABASE=0

_valid_hostname() {
  [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] && [[ "$1" == *.* ]]
}

usage() {
  sed -n '2,10p' "$0"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    --supabase-domain)
      SUPABASE_DOMAIN="${2:-}"
      shift 2
      ;;
    --clear-supabase)
      CLEAR_SUPABASE=1
      shift
      ;;
    -h | --help)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "apply-domain-tls.sh must run as root" >&2
  exit 1
fi

if [[ -z "${DOMAIN}" ]] || ! _valid_hostname "${DOMAIN}"; then
  echo "Valid --domain hostname required (e.g. broker.example.com)" >&2
  exit 1
fi

if [[ "${CLEAR_SUPABASE}" -eq 1 ]]; then
  SUPABASE_DOMAIN=""
elif [[ -n "${SUPABASE_DOMAIN}" ]] && ! _valid_hostname "${SUPABASE_DOMAIN}"; then
  echo "Invalid --supabase-domain hostname" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Config file missing: ${CONFIG_FILE}" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${INSTALL_DIR}/scripts/lib/install-common.sh"

_brokerai_upsert_config_kv "${CONFIG_FILE}" "BROKERAI_DOMAIN" "${DOMAIN}"
export BROKERAI_DOMAIN="${DOMAIN}"

if [[ -n "${SUPABASE_DOMAIN}" ]]; then
  _brokerai_upsert_config_kv "${CONFIG_FILE}" "BROKERAI_SUPABASE_DOMAIN" "${SUPABASE_DOMAIN}"
  export BROKERAI_SUPABASE_DOMAIN="${SUPABASE_DOMAIN}"
else
  # Remove public Supabase hostname; restore loopback Kong URL.
  if grep -q '^BROKERAI_SUPABASE_DOMAIN=' "${CONFIG_FILE}" 2>/dev/null; then
    sed -i '/^BROKERAI_SUPABASE_DOMAIN=/d' "${CONFIG_FILE}"
  fi
  unset BROKERAI_SUPABASE_DOMAIN || true
  _brokerai_upsert_config_kv "${CONFIG_FILE}" "BROKERAI_SUPABASE_URL" "http://127.0.0.1:8000"
fi

_brokerai_maybe_install_caddy_tls "${INSTALL_DIR}" "${CONFIG_FILE}"
systemctl restart brokerai-web || true

echo "Applied TLS for https://${DOMAIN}"
if [[ -n "${SUPABASE_DOMAIN}" ]]; then
  echo "Applied TLS for https://${SUPABASE_DOMAIN} (Kong + Studio)"
fi
