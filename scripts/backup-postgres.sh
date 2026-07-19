#!/usr/bin/env bash
# Logical Postgres dump for self-hosted Supabase (LXC / production).
#
# Dumps via docker exec into supabase-db, gzip-compresses to
# BROKERAI_BACKUP_DIR, and prunes files older than BROKERAI_BACKUP_RETENTION_DAYS.
#
# Usage:
#   ./scripts/backup-postgres.sh
#   BROKERAI_BACKUP_RETENTION_DAYS=14 ./scripts/backup-postgres.sh
set -euo pipefail

CONFIG_ENV="${BROKERAI_CONFIG_ENV:-/etc/brokerai/config.env}"
if [[ -f "${CONFIG_ENV}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${CONFIG_ENV}" && set +a
fi

BACKUP_DIR="${BROKERAI_BACKUP_DIR:-/var/lib/brokerai/backups/postgres}"
RETENTION_DAYS="${BROKERAI_BACKUP_RETENTION_DAYS:-7}"
CONTAINER="${BROKERAI_POSTGRES_CONTAINER:-supabase-db}"
DB_NAME="${BROKERAI_POSTGRES_DB:-postgres}"
DB_USER="${BROKERAI_POSTGRES_USER:-postgres}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Postgres backups" >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null | grep -qx true; then
  echo "Postgres container '${CONTAINER}' is not running" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 750 "${BACKUP_DIR}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
outfile="${BACKUP_DIR}/brokerai-postgres-${stamp}.sql.gz"
tmpfile="${outfile}.partial"

cleanup() {
  rm -f "${tmpfile}"
}
trap cleanup EXIT

echo "[backup] dumping ${DB_NAME} from ${CONTAINER} → ${outfile}"
docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl \
  | gzip -c >"${tmpfile}"
mv "${tmpfile}" "${outfile}"
chmod 640 "${outfile}"

# Prune old dumps (ignore non-matching files in the directory).
find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'brokerai-postgres-*.sql.gz' \
  -mtime "+${RETENTION_DAYS}" -print -delete || true

echo "[backup] complete ($(du -h "${outfile}" | awk '{print $1}'))"
echo "[backup] retention: ${RETENTION_DAYS} days under ${BACKUP_DIR}"
