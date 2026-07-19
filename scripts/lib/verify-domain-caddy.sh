#!/usr/bin/env bash
# Smoke-check dual-site Caddyfile generation (no root / no systemd).
#
# Usage (from repo root):
#   bash scripts/lib/verify-domain-caddy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMPDIR="${TMPDIR:-/tmp}"
OUT="${TMPDIR}/brokerai-caddy-verify-$$.Caddyfile"
SUPA_ENV="${TMPDIR}/brokerai-supabase-verify-$$.env"
trap 'rm -f "${OUT}" "${SUPA_ENV}"' EXIT

cat >"${SUPA_ENV}" <<'EOF'
DASHBOARD_USERNAME=supabase
DASHBOARD_PASSWORD=test-studio-password
EOF

export BROKERAI_CADDY_DRY_RUN=1
export BROKERAI_CADDYFILE="${OUT}"
export BROKERAI_INSTALL_DIR="${ROOT}"
export BROKERAI_SUPABASE_ENV="${SUPA_ENV}"
export BROKERAI_DOMAIN="broker.example.com"
export BROKERAI_SUPABASE_DOMAIN="supabase.example.com"
export BROKERAI_WEB_PORT=1989

bash "${ROOT}/scripts/lib/install-caddy.sh"

grep -q 'broker.example.com' "${OUT}"
grep -q 'supabase.example.com' "${OUT}"
grep -q '127.0.0.1:1989' "${OUT}"
grep -q '127.0.0.1:8000' "${OUT}"
grep -q '127.0.0.1:3000' "${OUT}"
grep -q '@supabase_api' "${OUT}"
grep -q 'basic_auth' "${OUT}"
grep -q 'supabase ' "${OUT}"

if command -v caddy >/dev/null 2>&1; then
  caddy validate --config "${OUT}" --adapter caddyfile
  echo "OK: Caddyfile validates with caddy"
else
  echo "OK: Caddyfile structure checks passed (caddy not installed — skip validate)"
fi
