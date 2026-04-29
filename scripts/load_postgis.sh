#!/bin/bash
# load_postgis.sh — Load GeoParquet or GeoJSON into PostGIS via ogr2ogr
# ======================================================================
# Usage:
#   ./scripts/load_postgis.sh data/sample/nairobi_wards.parquet geo.boundaries
#   ./scripts/load_postgis.sh data/buildings.geojson geo.points_of_interest
#   ./scripts/load_postgis.sh data/parcels.gpkg geo.parcels --layer parcels
#
# Requires: ogr2ogr (GDAL), running PostGIS container
# Install:  brew install gdal
#
# Behaviour:
#   - Appends to existing table by default (use --overwrite to replace)
#   - Reprojects to EPSG:4326 automatically
#   - Uses the Docker network host alias 'localhost' with exposed port 5432

set -euo pipefail

INPUT="${1:?Usage: $0 <input_file> <schema.table> [--layer LAYER] [--overwrite]}"
TARGET="${2:?Usage: $0 <input_file> <schema.table> [--layer LAYER] [--overwrite]}"
LAYER_ARG=""
UPDATE_FLAG="-append"

# Parse optional arguments
shift 2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --layer) LAYER_ARG="-nln $2"; shift 2 ;;
        --overwrite) UPDATE_FLAG="-overwrite"; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Load .env.local for connection details
if [ -f ".env.local" ]; then
    set -a; source .env.local; set +a
fi

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-geodata}"
DB_USER="${POSTGRES_USER:-geouser}"
DB_PASS="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD not set}"

PG_CONNECTION="PG:host=${DB_HOST} port=${DB_PORT} dbname=${DB_NAME} user=${DB_USER} password=${DB_PASS}"

echo "[load_postgis] Loading ${INPUT} → ${TARGET}"
echo "[load_postgis] Connection: ${DB_HOST}:${DB_PORT}/${DB_NAME}"

ogr2ogr \
    -f "PostgreSQL" \
    "${PG_CONNECTION}" \
    "${INPUT}" \
    -nln "${TARGET}" \
    -t_srs "EPSG:4326" \
    -lco "GEOMETRY_NAME=geom" \
    -lco "FID=id" \
    -lco "SPATIAL_INDEX=GIST" \
    ${LAYER_ARG} \
    ${UPDATE_FLAG} \
    --config PG_USE_COPY YES \
    -progress

echo "[load_postgis] Done. Rows in ${TARGET}:"
PGPASSWORD="${DB_PASS}" psql \
    -h "${DB_HOST}" -p "${DB_PORT}" \
    -U "${DB_USER}" -d "${DB_NAME}" \
    -c "SELECT COUNT(*) FROM ${TARGET};"
