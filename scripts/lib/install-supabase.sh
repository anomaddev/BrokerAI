#!/usr/bin/env bash
# Install Docker (if needed) and bootstrap self-hosted Supabase for BrokerAI on Debian/Ubuntu.
set -euo pipefail

INSTALL_DIR="${1:-/opt/brokerai}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker Engine"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but not running" >&2
  exit 1
fi

chmod +x "${INSTALL_DIR}/scripts/setup-supabase.sh"
"${INSTALL_DIR}/scripts/setup-supabase.sh" --start

# Apply schema
if [[ -x "${INSTALL_DIR}/venv/bin/python" ]]; then
  (
    cd "${INSTALL_DIR}"
    set -a
    # shellcheck disable=SC1091
    source /etc/brokerai/config.env
    set +a
    "${INSTALL_DIR}/venv/bin/python" -c "import asyncio; from brokerai.db.indexes import ensure_indexes; asyncio.run(ensure_indexes())" || true
  )
fi

echo "Supabase ready"
