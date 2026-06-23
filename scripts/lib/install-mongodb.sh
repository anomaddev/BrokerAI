#!/usr/bin/env bash
# Install MongoDB Community Server (localhost-only) on Debian/Ubuntu.
set -euo pipefail

if command -v mongod >/dev/null 2>&1; then
  echo "MongoDB already installed"
  exit 0
fi

# shellcheck source=/dev/null
source /etc/os-release

MONGO_MAJOR="8.0"
KEYRING="/usr/share/keyrings/mongodb-server-${MONGO_MAJOR}.gpg"
LIST_FILE="/etc/apt/sources.list.d/mongodb-org-${MONGO_MAJOR}.list"
GPG_APT_CONF="/etc/apt/apt.conf.d/99brokerai-mongodb-gpg"

_mongodb_debian_suite() {
  case "${VERSION_CODENAME:-bookworm}" in
    trixie | forky | sid | testing | unstable)
      # MongoDB does not publish Trixie packages yet; Bookworm binaries work on Debian 13.
      echo "bookworm"
      ;;
    bookworm | bullseye)
      echo "${VERSION_CODENAME}"
      ;;
    *)
      echo "bookworm"
      ;;
  esac
}

_mongodb_ubuntu_codename() {
  case "${VERSION_CODENAME:-}" in
    noble) echo "noble" ;;
    jammy) echo "jammy" ;;
    *)
      echo "noble"
      ;;
  esac
}

_ensure_gnupg() {
  if ! command -v gpg >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gnupg ca-certificates curl
  fi
}

# Debian 13+ apt (sequoia/sqv) rejects MongoDB's legacy SHA1-bound signing keys.
_enable_legacy_gpg_for_apt() {
  if [[ -f "$GPG_APT_CONF" ]]; then
    return 0
  fi
  if [[ "${ID:-}" != "debian" ]]; then
    return 0
  fi
  if [[ "${VERSION_CODENAME:-}" == "trixie" || "${VERSION_ID:-0}" -ge 13 ]]; then
    echo 'APT::Key::GPGCommand "/usr/bin/gpg";' >"$GPG_APT_CONF"
  fi
}

_ensure_gnupg
_enable_legacy_gpg_for_apt

# Remove stale MongoDB apt entries from prior failed installs (e.g. trixie/7.0).
rm -f /etc/apt/sources.list.d/mongodb-org-*.list
rm -f /usr/share/keyrings/mongodb-server-*.gpg

MONGO_REPO_LABEL="unknown"

if [[ "${ID:-}" == "ubuntu" ]]; then
  MONGO_REPO_LABEL="$(_mongodb_ubuntu_codename)"
  curl -fsSL "https://pgp.mongodb.com/server-${MONGO_MAJOR}.asc" | gpg -o "$KEYRING" --dearmor
  echo "deb [ arch=amd64,arm64 signed-by=${KEYRING} ] https://repo.mongodb.org/apt/ubuntu ${MONGO_REPO_LABEL}/mongodb-org/${MONGO_MAJOR} multiverse" \
    >"$LIST_FILE"
else
  MONGO_REPO_LABEL="$(_mongodb_debian_suite)"
  curl -fsSL "https://pgp.mongodb.com/server-${MONGO_MAJOR}.asc" | gpg -o "$KEYRING" --dearmor
  echo "deb [ arch=amd64,arm64 signed-by=${KEYRING} ] https://repo.mongodb.org/apt/debian ${MONGO_REPO_LABEL}/mongodb-org/${MONGO_MAJOR} main" \
    >"$LIST_FILE"
fi

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mongodb-org

mkdir -p /var/lib/mongodb /var/log/mongodb
cat > /etc/mongod.conf <<'EOF'
storage:
  dbPath: /var/lib/mongodb
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log
net:
  port: 27017
  bindIp: 127.0.0.1
processManagement:
  timeZoneInfo: /usr/share/zoneinfo
EOF

systemctl enable --now mongod
echo "MongoDB ${MONGO_MAJOR} installed (repo: ${MONGO_REPO_LABEL}) on 127.0.0.1:27017"
