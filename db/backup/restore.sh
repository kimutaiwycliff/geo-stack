#!/bin/bash
# restore.sh — Download latest backup from R2 and restore to PostGIS
# =================================================================
# Usage:
#   ./db/backup/restore.sh                           # Restore latest backup
#   ./db/backup/restore.sh backups/2025/01/file.sql.gz  # Restore specific file
#
# WARNING: This will DROP and recreate the database. Run on a test instance first.
# Requires env vars: PGPASSWORD, POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER,
#                    R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET_NAME

set -euo pipefail

BUCKET="${R2_BUCKET_NAME:-geo-data}"
ENDPOINT="${R2_ENDPOINT}"
LOCAL_FILE="/tmp/restore_$(date +%Y%m%d_%H%M%S).sql.gz"

if [ -n "${1:-}" ]; then
  RESTORE_KEY="$1"
else
  # Find the most recent backup
  echo "[restore] Finding latest backup in s3://${BUCKET}/backups/..."
  RESTORE_KEY=$(
    AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}" \
    AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}" \
    aws s3 ls "s3://${BUCKET}/backups/" \
      --endpoint-url="${ENDPOINT}" \
      --recursive \
    | sort | tail -1 | awk '{print $4}'
  )
  echo "[restore] Latest backup: ${RESTORE_KEY}"
fi

echo "[restore] Downloading s3://${BUCKET}/${RESTORE_KEY}..."
AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}" \
aws s3 cp "s3://${BUCKET}/${RESTORE_KEY}" "${LOCAL_FILE}" \
  --endpoint-url="${ENDPOINT}"

echo "[restore] Download complete. Restoring to ${POSTGRES_DB:-geodata}..."
echo "[restore] THIS WILL OVERWRITE THE CURRENT DATABASE. Press Ctrl+C to abort."
sleep 5

pg_restore \
  --host="${POSTGRES_HOST:-postgis}" \
  --username="${POSTGRES_USER:-geouser}" \
  --dbname="${POSTGRES_DB:-geodata}" \
  --no-password \
  --clean \
  --if-exists \
  --verbose \
  "${LOCAL_FILE}"

rm -f "${LOCAL_FILE}"
echo "[restore] Restore complete at $(date)"
