#!/usr/bin/env bash
# Build the React frontend into src/brokerai/web/static
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found — install Node.js first" >&2
  exit 1
fi

npm ci --silent 2>/dev/null || npm install --silent
npm run build --silent
echo "Frontend built to src/brokerai/web/static"
