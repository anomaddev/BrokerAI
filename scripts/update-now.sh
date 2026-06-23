#!/usr/bin/env bash
# Copyright (c) 2021-2026 anomaddev
# License: MIT
# Source: https://github.com/anomaddev/BrokerAI
#
# Manually trigger an update — for fast development and testing.
#
# Usage:
#   sudo ./scripts/update-now.sh          # inside container (recommended)
#   ./scripts/update-now.sh               # uses systemd or dev fallback

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTO_UPDATE="${ROOT}/scripts/auto-update.sh"

if [[ $EUID -eq 0 && -x "${AUTO_UPDATE}" ]]; then
  exec "${AUTO_UPDATE}" --force
fi

if command -v systemctl &>/dev/null && systemctl cat brokerai-update.service &>/dev/null 2>&1; then
  sudo -n systemctl start brokerai-update.service 2>/dev/null \
    || sudo systemctl start brokerai-update.service
  echo "Update triggered via systemd."
  echo "Watch progress: tail -f /var/log/brokerai/update.log"
  exit 0
fi

if [[ -x "${AUTO_UPDATE}" ]]; then
  echo "Run as root: sudo ${AUTO_UPDATE} --force" >&2
  exit 1
fi

if [[ -f "${ROOT}/pyproject.toml" ]]; then
  echo "Dev mode: pulling latest and refreshing local venv..."
  cd "${ROOT}"
  git pull
  if [[ -d venv ]]; then
    venv/bin/pip install -r requirements.txt -q
    venv/bin/pip install -e . -q
  elif [[ -d .venv ]]; then
    .venv/bin/pip install -r requirements.txt -q
    .venv/bin/pip install -e . -q
  else
    pip install -r requirements.txt -q
    pip install -e . -q
  fi
  echo "Dev update complete. Restart the orchestrator and web UI if they are running."
  exit 0
fi

echo "No update method available." >&2
exit 1
