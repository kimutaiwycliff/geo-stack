#!/bin/bash
# backup.sh — pg_dump and upload to Cloudflare R2
# ================================================
# Usage (manual):
#   docker compose --profile backup run --rm backup
#
# Usage (nightly cron on VPS):
#   0 2 * * * cd /opt/geo-stack && docker compose --profile backup run --rm backup
#
# Requires env vars: PGPASSWORD, POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER,
#                    R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET_NAME

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="/tmp/geodata_${TIMESTAMP}.sql.gz"

echo "[backup] Starting pg_dump at $(date)"

pg_dump \
  --host="${POSTGRES_HOST:-postgis}" \
  --username="${POSTGRES_USER:-geouser}" \
  --dbname="${POSTGRES_DB:-geodata}" \
  --format=custom \
  --compress=9 \
  --no-password \
  | gzip > "${DUMP_FILE}"

SIZE=$(du -sh "${DUMP_FILE}" | cut -f1)
echo "[backup] Dump complete: ${DUMP_FILE} (${SIZE})"

# Upload to R2 using curl (AWS Signature V4)
# aws CLI or rclone would be cleaner but adds image weight
BUCKET="${R2_BUCKET_NAME:-geo-data}"
KEY="backups/$(date +%Y/%m)/geodata_${TIMESTAMP}.sql.gz"
ENDPOINT="${R2_ENDPOINT}"

if [ -z "${R2_ENDPOINT:-}" ] || [ -z "${R2_ACCESS_KEY:-}" ]; then
  echo "[backup] R2 not configured — skipping upload (dump saved to ${DUMP_FILE})"
  exit 0
fi

# Use aws-cli if available, otherwise fall back to a signed curl upload
if command -v aws &> /dev/null; then
  AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}" \
  AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}" \
  aws s3 cp "${DUMP_FILE}" "s3://${BUCKET}/${KEY}" \
    --endpoint-url="${ENDPOINT}" \
    --no-progress
else
  echo "[backup] aws CLI not found — install it in the backup image for R2 upload"
  echo "[backup] Dump available locally at ${DUMP_FILE}"
  exit 1
fi

echo "[backup] Uploaded to s3://${BUCKET}/${KEY}"
rm -f "${DUMP_FILE}"

# Prune backups older than 30 days
echo "[backup] Pruning backups older than 30 days..."
CUTOFF=$(date -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)
AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}" \
aws s3 ls "s3://${BUCKET}/backups/" \
  --endpoint-url="${ENDPOINT}" \
  --recursive \
  | awk -v cutoff="${CUTOFF}" '$1 < cutoff {print $4}' \
  | while read -r key; do
      AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}" \
      AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}" \
      aws s3 rm "s3://${BUCKET}/${key}" --endpoint-url="${ENDPOINT}"
      echo "[backup] Deleted old backup: ${key}"
    done

echo "[backup] Done at $(date)"
