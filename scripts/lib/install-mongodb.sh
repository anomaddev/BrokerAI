#!/usr/bin/env bash
# Install MongoDB Community Server (localhost-only) on Debian/Ubuntu.
set -euo pipefail

if command -v mongod >/dev/null 2>&1; then
  echo "MongoDB already installed"
  exit 0
fi

# shellcheck source=/dev/null
source /etc/os-release
CODENAME="${VERSION_CODENAME:-bookworm}"

curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/debian ${CODENAME}/mongodb-org/7.0 main" \
  > /etc/apt/sources.list.d/mongodb-org-7.0.list

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mongodb-org

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
echo "MongoDB installed and bound to 127.0.0.1:27017"
