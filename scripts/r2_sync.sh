#!/bin/bash
# r2_sync.sh — Sync local data files to Cloudflare R2
# =====================================================
# Usage:
#   ./scripts/r2_sync.sh                              # sync entire data/ folder
#   ./scripts/r2_sync.sh data/pmtiles/                # sync pmtiles only
#   ./scripts/r2_sync.sh data/pmtiles/ pmtiles/       # sync to R2 subfolder
#   ./scripts/r2_sync.sh projects/foo/data/ foo/      # sync project data to foo/ prefix
#   ./scripts/r2_sync.sh data/sample/nairobi.parquet  # single file
#
# Requires: aws CLI (works with R2 via --endpoint-url)
# Install:  brew install awscli
#
# Credentials loaded from environment. For cloud mode:
#   source projects/<name>/.env
# For local dev:
#   source .env.local   or   source .env

set -euo pipefail

LOCAL_PATH="${1:-data/}"
REMOTE_PREFIX="${2:-}"   # Optional R2 subfolder prefix, e.g. "pmtiles/" or "project-name/"

# Load env vars — prefer project .env, fall back to repo root
for env_file in "${ENV_FILE:-}" projects/*/.env .env.cloud .env.local .env; do
    if [ -n "$env_file" ] && [ -f "$env_file" ]; then
        set -a; source "$env_file"; set +a
        break
    fi
done

R2_ENDPOINT="${R2_ENDPOINT:?R2_ENDPOINT not set. Source your .env file first.}"
R2_ACCESS_KEY="${R2_ACCESS_KEY:?R2_ACCESS_KEY not set}"
R2_SECRET_KEY="${R2_SECRET_KEY:?R2_SECRET_KEY not set}"
R2_BUCKET_NAME="${R2_BUCKET_NAME:-geo-data}"

# Build destination S3 path
# If a remote prefix is given, use it directly; otherwise derive from local path.
if [ -n "$REMOTE_PREFIX" ]; then
    S3_DEST="s3://${R2_BUCKET_NAME}/${REMOTE_PREFIX%/}"
else
    REL_PATH="${LOCAL_PATH#data/}"
    S3_DEST="s3://${R2_BUCKET_NAME}/${REL_PATH%/}"
fi

echo "[r2_sync] ${LOCAL_PATH} → ${S3_DEST}"
echo "[r2_sync] Endpoint: ${R2_ENDPOINT}"

export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_KEY}"

if [ -f "${LOCAL_PATH}" ]; then
    aws s3 cp "${LOCAL_PATH}" "${S3_DEST}" \
        --endpoint-url="${R2_ENDPOINT}" \
        --no-progress
else
    aws s3 sync "${LOCAL_PATH}" "${S3_DEST}" \
        --endpoint-url="${R2_ENDPOINT}" \
        --exclude "*.gitkeep" \
        --exclude ".DS_Store" \
        --no-progress
fi

echo "[r2_sync] Done."
echo ""
if [ -n "${R2_PUBLIC_URL:-}" ]; then
    echo "Public URL: ${R2_PUBLIC_URL}/${REMOTE_PREFIX:-}"
fi
