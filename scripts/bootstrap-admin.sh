#!/usr/bin/env bash
# Create the initial BrokerAI admin from install-time credentials (optional).
set -euo pipefail

if [[ -f /root/brokerai-bootstrap.env ]]; then
  # shellcheck disable=SC1091
  source /root/brokerai-bootstrap.env
  rm -f /root/brokerai-bootstrap.env
fi

USERNAME="${BROKERAI_ADMIN_USER:-}"
PASSWORD="${BROKERAI_ADMIN_PASSWORD:-}"

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
  exit 0
fi

INSTALL_DIR="${BROKERAI_INSTALL_DIR:-/opt/brokerai}"
CONFIG_FILE="${BROKERAI_CONFIG_DIR:-/etc/brokerai}/config.env"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$CONFIG_FILE" && set +a
fi

if [[ "${BROKERAI_AUTH_MODE:-builtin}" == "oidc" ]]; then
  echo "OIDC auth enabled — skipping built-in admin bootstrap"
  exit 0
fi

export BROKERAI_ADMIN_USER BROKERAI_ADMIN_PASSWORD

"${INSTALL_DIR}/venv/bin/python" <<'PY'
import os
import sys

from brokerai.auth import AuthStore, hash_password, is_valid_username, validate_password
from brokerai.auth.password import PasswordValidationError

username = os.environ.get("BROKERAI_ADMIN_USER", "")
password = os.environ.get("BROKERAI_ADMIN_PASSWORD", "")

if not username or not password:
    sys.exit(0)

if not is_valid_username(username):
    print(f"Invalid username: {username}", file=sys.stderr)
    sys.exit(1)

try:
    validate_password(password, password)
except PasswordValidationError as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)

store = AuthStore()
if store.is_setup_complete():
    print("Setup already complete — skipping bootstrap")
    sys.exit(0)

store.create_user(username, hash_password(password))
print(f"Bootstrapped admin user: {username}")
PY

printf '%s\n' "$PASSWORD" | "${INSTALL_DIR}/scripts/provision-admin-user.sh" "$USERNAME" || {
  echo "Warning: SSH provisioning failed — web login is still configured" >&2
}

AUTH_DIR="${BROKERAI_DATA_DIR:-/var/lib/brokerai/data}/auth"
if [[ -d "$AUTH_DIR" ]]; then
  chown -R brokerai:brokerai "$AUTH_DIR"
  chmod 750 "$AUTH_DIR"
  [[ -f "${AUTH_DIR}/users.json" ]] && chmod 640 "${AUTH_DIR}/users.json"
fi

echo "BrokerAI admin account ready for login"
