#!/bin/bash
# to_pmtiles.sh — Generate PMTiles from GeoJSON or GeoParquet
# ============================================================
# Usage:
#   ./scripts/to_pmtiles.sh data/sample/nairobi_wards.parquet data/pmtiles/nairobi_wards.pmtiles
#   ./scripts/to_pmtiles.sh data/buildings.geojson data/pmtiles/buildings.pmtiles --max-zoom 16
#
# Requires: tippecanoe, pmtiles CLI, duckdb CLI
#   brew install tippecanoe
#   brew install protomaps/homebrew-protomaps/go-pmtiles
#   brew install duckdb
#
# Process:
#   1. If input is .parquet: export to GeoJSON via DuckDB first
#   2. Run tippecanoe to generate .mbtiles
#   3. Convert .mbtiles → .pmtiles via pmtiles convert
#   4. Run pmtiles verify to confirm output is valid
#   5. Print upload command for Cloudflare R2

set -euo pipefail

INPUT="${1:?Usage: $0 <input.(parquet|geojson)> <output.pmtiles> [--max-zoom N]}"
OUTPUT="${2:?Usage: $0 <input.(parquet|geojson)> <output.pmtiles> [--max-zoom N]}"
MAX_ZOOM="${3:---max-zoom=14}"

# Strip --max-zoom= prefix if passed as positional
[[ "${MAX_ZOOM}" =~ ^[0-9]+$ ]] && MAX_ZOOM="--max-zoom=${MAX_ZOOM}"

LAYER_NAME=$(basename "${INPUT%.*}")
TMPDIR_PATH=$(mktemp -d)
GEOJSON_PATH="${TMPDIR_PATH}/${LAYER_NAME}.geojson"
MBTILES_PATH="${TMPDIR_PATH}/${LAYER_NAME}.mbtiles"

cleanup() { rm -rf "${TMPDIR_PATH}"; }
trap cleanup EXIT

# ---- Step 1: Convert Parquet → GeoJSON via DuckDB ----
if [[ "${INPUT}" == *.parquet ]]; then
    echo "[to_pmtiles] Exporting GeoParquet → GeoJSON via DuckDB..."
    if ! command -v duckdb &>/dev/null; then
        echo "ERROR: duckdb CLI not found. Install: brew install duckdb"
        exit 1
    fi
    duckdb -c "
        INSTALL spatial; LOAD spatial;
        COPY (
            SELECT ST_AsGeoJSON(ST_GeomFromWKB(geometry)) AS geometry,
                   * EXCLUDE (geometry, bbox_xmin, bbox_xmax, bbox_ymin, bbox_ymax)
            FROM read_parquet('${INPUT}')
            WHERE geometry IS NOT NULL
        ) TO '${GEOJSON_PATH}' (FORMAT JSON, ARRAY true);
    "
    echo "[to_pmtiles] Exported to ${GEOJSON_PATH}"
else
    GEOJSON_PATH="${INPUT}"
fi

# ---- Step 2: tippecanoe → .mbtiles ----
if ! command -v tippecanoe &>/dev/null; then
    echo "ERROR: tippecanoe not found. Install: brew install tippecanoe"
    exit 1
fi

echo "[to_pmtiles] Running tippecanoe..."
tippecanoe \
    --output="${MBTILES_PATH}" \
    --layer="${LAYER_NAME}" \
    --name="${LAYER_NAME}" \
    --attribution="geo-stack" \
    --minimum-zoom=0 \
    "${MAX_ZOOM}" \
    --drop-densest-as-needed \
    --extend-zooms-if-still-dropping \
    --force \
    "${GEOJSON_PATH}"

# ---- Step 3: mbtiles → pmtiles ----
if ! command -v pmtiles &>/dev/null; then
    echo "ERROR: pmtiles CLI not found. Install: brew install protomaps/homebrew-protomaps/go-pmtiles"
    exit 1
fi

mkdir -p "$(dirname "${OUTPUT}")"
echo "[to_pmtiles] Converting .mbtiles → .pmtiles..."
pmtiles convert "${MBTILES_PATH}" "${OUTPUT}"

# ---- Step 4: Verify ----
echo "[to_pmtiles] Verifying output..."
pmtiles verify "${OUTPUT}"

SIZE=$(du -sh "${OUTPUT}" | cut -f1)
echo "[to_pmtiles] Done: ${OUTPUT} (${SIZE})"
echo ""
echo "Next steps:"
echo "  Upload to R2:   ./scripts/r2_sync.sh data/pmtiles/"
echo "  Or serve local: pmtiles serve data/pmtiles/ --port 8081"
