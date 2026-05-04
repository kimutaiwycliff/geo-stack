#!/bin/bash
# load_supabase.sh — Load any vector format directly into Supabase PostGIS
# =========================================================================
# Supports: Shapefile (.shp or .zip), GeoJSON, GeoPackage (.gpkg),
#           GeoParquet (.parquet), KML, CSV, and any format GDAL can read.
#
# Usage:
#   ./scripts/load_supabase.sh <input_file> <schema.table> [OPTIONS]
#
# Examples:
#   # Shapefile zip → new staging table (auto-created)
#   ./scripts/load_supabase.sh data/kenya_admin.zip staging.kenya_admin
#
#   # GeoJSON → existing geo table (append)
#   ./scripts/load_supabase.sh data/wards.geojson staging.wards
#
#   # GeoPackage, specific layer, overwrite
#   ./scripts/load_supabase.sh data/kenya.gpkg staging.roads --layer roads --overwrite
#
#   # GeoParquet → staging
#   ./scripts/load_supabase.sh data/buildings.parquet staging.buildings
#
# Options:
#   --layer NAME    Source layer name (required for GeoPackage with multiple layers)
#   --overwrite     Drop and recreate the target table
#   --append        Append to existing table (default)
#   --where EXPR    OGR WHERE filter expression
#   --bbox W,S,E,N  Clip to bounding box before loading
#
# Environment:
#   SUPABASE_DIRECT_URL  Direct connection string (NOT the pooler).
#                        Get from: Supabase Dashboard → Project Settings →
#                        Database → Connection string → URI (direct)
#                        Format: postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres
#
#   .env.cloud, .env.local, .env are loaded automatically if present.
#
# Requires: GDAL (ogr2ogr)
#   macOS:  brew install gdal
#   Ubuntu: sudo apt install gdal-bin
#   Docker: use the geo-stack local Docker setup which includes GDAL

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────────
INPUT="${1:?Usage: $0 <input_file> <schema.table> [--layer NAME] [--overwrite] [--where EXPR] [--bbox W,S,E,N]}"
TARGET="${2:?Usage: $0 <input_file> <schema.table>}"
shift 2

OGR_LAYER=""
UPDATE_FLAG="-append"
WHERE_CLAUSE=""
BBOX_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --layer)     OGR_LAYER="-nln_alias '$2'"; shift 2 ;;
        --overwrite) UPDATE_FLAG="-overwrite"; shift ;;
        --append)    UPDATE_FLAG="-append"; shift ;;
        --where)     WHERE_CLAUSE="-where '$2'"; shift 2 ;;
        --bbox)
            IFS=',' read -r W S E N <<< "$2"
            BBOX_ARG="-spat $W $S $E $N"
            shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Load env vars ──────────────────────────────────────────────────────────
# Use a temp file export to avoid set -euo pipefail interfering with source
for ENV_FILE in .env.cloud .env.local .env; do
    if [ -f "$ENV_FILE" ]; then
        echo "[load_supabase] Sourcing $ENV_FILE"
        # grep out KEY=VALUE lines (skip comments and blanks), then export each
        while IFS='=' read -r key rest; do
            [[ -z "$key" || "$key" == \#* ]] && continue
            export "$key"="$rest"
        done < <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | grep '=')
        break
    fi
done

# ── Validate prerequisites ─────────────────────────────────────────────────
if [ -z "${SUPABASE_DIRECT_URL:-}" ]; then
    echo ""
    echo "ERROR: SUPABASE_DIRECT_URL is not set."
    echo ""
    echo "Set it in your .env.cloud file or as an environment variable:"
    echo "  export SUPABASE_DIRECT_URL='postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres'"
    echo ""
    echo "Get the URL from:"
    echo "  Supabase Dashboard → Project Settings → Database → Connection string → URI"
    echo "  Choose the DIRECT connection (NOT the pooler/PgBouncer URL)."
    echo "  The direct host looks like: db.XXXX.supabase.co (not aws-0-*.pooler.supabase.com)"
    exit 1
fi

if ! command -v ogr2ogr &>/dev/null; then
    echo "ERROR: ogr2ogr not found."
    echo "Install GDAL:"
    echo "  macOS:  brew install gdal"
    echo "  Ubuntu: sudo apt install gdal-bin"
    exit 1
fi

# ── Special handling for ZIP containing one or more shapefiles ─────────────
ACTUAL_INPUT="$INPUT"
TMP_DIR=""
if [[ "$(echo "$INPUT" | tr '[:upper:]' '[:lower:]')" == *.zip ]]; then
    TMP_DIR=$(mktemp -d)
    echo "[load_supabase] Extracting ZIP: $INPUT"
    unzip -q "$INPUT" -d "$TMP_DIR"

    # Count how many shapefiles are inside
    SHP_COUNT=$(find "$TMP_DIR" -name "*.shp" | wc -l | tr -d ' ')

    if [ "$SHP_COUNT" -eq 0 ]; then
        echo "ERROR: No .shp file found inside $INPUT"
        rm -rf "$TMP_DIR"
        exit 1
    elif [ "$SHP_COUNT" -gt 1 ]; then
        echo ""
        echo "[load_supabase] ZIP contains $SHP_COUNT shapefiles:"
        find "$TMP_DIR" -name "*.shp" | sort | while read -r f; do
            echo "  $(basename "$f" .shp)"
        done
        echo ""
        echo "  Hint: load a specific layer with --layer <basename>:"
        echo "    $0 $INPUT $TARGET --layer adminareas"
        echo ""
        # If --layer was given, filter to that SHP
        if [ -n "$OGR_LAYER" ]; then
            LAYER_NAME=$(echo "$OGR_LAYER" | sed "s/-nln_alias '//;s/'//")
            SHP_FILE=$(find "$TMP_DIR" -name "*${LAYER_NAME}*.shp" | head -1)
            if [ -z "$SHP_FILE" ]; then
                echo "ERROR: No shapefile matching '${LAYER_NAME}' found in ZIP."
                rm -rf "$TMP_DIR"
                exit 1
            fi
            OGR_LAYER=""   # nln_alias not needed; we use -nln TARGET below
        else
            SHP_FILE=$(find "$TMP_DIR" -name "*.shp" | sort | head -1)
            echo "[load_supabase] Loading first layer: $(basename "$SHP_FILE")"
            echo "[load_supabase] Re-run with --layer <name> to load a specific layer."
        fi
    else
        SHP_FILE=$(find "$TMP_DIR" -name "*.shp")
    fi

    ACTUAL_INPUT="$SHP_FILE"
    echo "[load_supabase] Shapefile: $(basename "$SHP_FILE")"
fi

cleanup() {
    if [ -n "$TMP_DIR" ]; then rm -rf "$TMP_DIR"; fi
}
trap cleanup EXIT

# ── Run ogr2ogr ────────────────────────────────────────────────────────────
echo ""
echo "[load_supabase] ──────────────────────────────────────────────"
echo "[load_supabase] Input:   $INPUT"
echo "[load_supabase] Target:  $TARGET (Supabase)"
echo "[load_supabase] Mode:    ${UPDATE_FLAG/-/}"
echo "[load_supabase] ──────────────────────────────────────────────"
echo ""

# Build PG connection string: append sslmode only if not already in the URL
PG_CONN="${SUPABASE_DIRECT_URL}"
if [[ "$PG_CONN" != *sslmode* ]]; then
    # URL format: append as query param; key=value format: append with space
    if [[ "$PG_CONN" == postgresql://* || "$PG_CONN" == postgres://* ]]; then
        if [[ "$PG_CONN" == *\?* ]]; then
            PG_CONN="${PG_CONN}&sslmode=require"
        else
            PG_CONN="${PG_CONN}?sslmode=require"
        fi
    else
        PG_CONN="${PG_CONN} sslmode=require"
    fi
fi

ogr2ogr \
    -f "PostgreSQL" \
    "PG:${PG_CONN}" \
    "${ACTUAL_INPUT}" \
    -nln "${TARGET}" \
    -t_srs "EPSG:4326" \
    -lco "GEOMETRY_NAME=geom" \
    -lco "FID=id" \
    -lco "SPATIAL_INDEX=GIST" \
    -lco "SCHEMA=$(echo $TARGET | cut -d. -f1)" \
    ${OGR_LAYER} \
    ${WHERE_CLAUSE} \
    ${BBOX_ARG} \
    ${UPDATE_FLAG} \
    --config PG_USE_COPY YES \
    --config OGR_TRUNCATE NO \
    -progress

echo ""
echo "[load_supabase] ✓ Done. Counting rows in ${TARGET}..."
PGPASSWORD=$(echo "$SUPABASE_DIRECT_URL" | grep -oP '(?<=:)[^@]+(?=@)') \
PGHOST=$(echo "$SUPABASE_DIRECT_URL" | grep -oP '(?<=@)[^:]+') \
PGPORT=5432 \
PGDATABASE=postgres \
PGUSER=$(echo "$SUPABASE_DIRECT_URL" | grep -oP '(?<=//)[^:]+') \
psql "$SUPABASE_DIRECT_URL" -c "SELECT COUNT(*) AS rows FROM ${TARGET};" 2>/dev/null || true

echo ""
echo "[load_supabase] ── Next steps ──────────────────────────────────"
echo "  Explore in SQL Editor:    SELECT * FROM ${TARGET} LIMIT 10;"
echo "  Check geometry:           SELECT ST_IsValid(geom), COUNT(*) FROM ${TARGET} GROUP BY 1;"
echo "  To GeoParquet:            python scripts/to_geoparquet.py ${INPUT} data/$(basename ${TARGET}).parquet"
echo "  To PMTiles:               ./scripts/to_pmtiles.sh ${INPUT} data/pmtiles/$(basename ${TARGET}).pmtiles"
echo "  Upload PMTiles to R2:     ./scripts/r2_sync.sh data/pmtiles/"
echo "──────────────────────────────────────────────────────────────────"
