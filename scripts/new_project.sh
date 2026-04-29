#!/bin/bash
# new_project.sh — Bootstrap a new geospatial project on the free stack
# ======================================================================
# Usage:
#   ./scripts/new_project.sh <project-name>
#   ./scripts/new_project.sh nairobi-flood-risk
#
# Creates:
#   projects/<name>/             — project workspace
#   projects/<name>/data/        — local data files (gitignored)
#   projects/<name>/sql/         — project-specific SQL overrides
#   projects/<name>/.env         — project-specific cloud env (gitignored)
#   projects/<name>/layers.ts    — layer config stub to copy into frontend/

set -e

PROJECT=$1
if [ -z "$PROJECT" ]; then
  echo "Usage: ./scripts/new_project.sh <project-name>"
  echo "Example: ./scripts/new_project.sh nairobi-flood-risk"
  exit 1
fi

SLUG="${PROJECT//-/_}"   # hyphens → underscores for SQL identifiers

echo ""
echo "=== Bootstrapping: $PROJECT ==="
echo ""

# --- Create directories -------------------------------------------------------
mkdir -p "projects/$PROJECT/data"
mkdir -p "projects/$PROJECT/sql"

# --- Copy base SQL files ------------------------------------------------------
cp db/init/00_extensions.sql "projects/$PROJECT/sql/"
cp db/init/01_schemas.sql    "projects/$PROJECT/sql/"
cp db/init/02_tables.sql     "projects/$PROJECT/sql/"
cp db/init/03_indexes.sql    "projects/$PROJECT/sql/"
cp db/init/04_functions.sql  "projects/$PROJECT/sql/"

# --- Create project .env from cloud example -----------------------------------
cp .env.cloud.example "projects/$PROJECT/.env"
# Swap default bucket name to project slug
sed -i '' "s/geo-data/$PROJECT/g" "projects/$PROJECT/.env" 2>/dev/null \
  || sed -i "s/geo-data/$PROJECT/g" "projects/$PROJECT/.env"

# --- Create layer config stub -------------------------------------------------
cat > "projects/$PROJECT/layers.ts" << LAYERS
/**
 * layers.ts stub for: $PROJECT
 * Generated: $(date +%Y-%m-%d)
 *
 * Copy relevant entries into frontend/src/lib/config/layers.ts
 *
 * Layer type quick guide:
 *   'mvt'      → live data, changes daily      → Martin reads from PostGIS
 *   'pmtiles'  → static data, rarely changes   → browser fetches from R2 directly
 *   'geojson'  → needs server-side filtering   → FastAPI + DuckDB + GeoParquet on R2
 *   'raster'   → DEM, imagery, continuous data → TiTiler + COG on R2
 */

export const ${SLUG}Layers = [
  {
    id: '${PROJECT}-boundaries',
    label: 'Boundaries',
    type: 'pmtiles' as const,
    url: 'pmtiles://\${PUBLIC_R2_URL}/${PROJECT}/boundaries.pmtiles',
    sourceLayer: '${SLUG}_boundaries',
    paint: {
      'fill-color': '#1D9E75',
      'fill-opacity': 0.15,
      'fill-outline-color': '#0F6E56',
    },
    visible: true,
    popupFields: ['name', 'code'],
  },
  // Add more layers below. See frontend/src/lib/config/layers.ts for full examples.
];
LAYERS

echo "Created:"
echo "  projects/$PROJECT/"
echo "  projects/$PROJECT/data/         (gitignored — put local data files here)"
echo "  projects/$PROJECT/sql/          (project SQL, copy to Supabase SQL Editor)"
echo "  projects/$PROJECT/.env          (fill in Supabase + R2 credentials)"
echo "  projects/$PROJECT/layers.ts     (layer config stub)"
echo ""
echo "========================================================================"
echo "NEXT STEPS (~10 minutes)"
echo "========================================================================"
echo ""
echo "1. CREATE SUPABASE PROJECT"
echo "   → https://supabase.com/dashboard → New project"
echo "   → Name: $PROJECT  |  Region: closest to your users"
echo "   → Run in SQL Editor (in order):"
echo "       hosting/supabase/setup.sql"
echo "       projects/$PROJECT/sql/02_tables.sql"
echo "       projects/$PROJECT/sql/03_indexes.sql"
echo "       projects/$PROJECT/sql/04_functions.sql"
echo "   → Copy pooler URL to projects/$PROJECT/.env → SUPABASE_DATABASE_URL"
echo "     (Dashboard → Project Settings → Database → Connection string → URI pooler)"
echo ""
echo "2. LOAD YOUR DATA"
echo "   # Vector → GeoParquet (for DuckDB analytics layers)"
echo "   python scripts/to_geoparquet.py input.geojson projects/$PROJECT/data/$PROJECT.parquet"
echo ""
echo "   # Vector → PostGIS (for live MVT layers)"
echo "   source projects/$PROJECT/.env"
echo "   ogr2ogr -f PostgreSQL PG:\"\$SUPABASE_DATABASE_URL\" input.geojson \\"
echo "     -nln geo.my_layer -lco GEOMETRY_NAME=geom -lco FID=id"
echo ""
echo "   # GeoParquet → PMTiles (for static layers served from R2)"
echo "   ./scripts/to_pmtiles.sh projects/$PROJECT/data/$PROJECT.parquet \\"
echo "     data/pmtiles/$PROJECT.pmtiles --max-zoom 16"
echo ""
echo "3. SYNC DATA TO R2"
echo "   source projects/$PROJECT/.env"
echo "   ./scripts/r2_sync.sh data/pmtiles/ pmtiles/   # PMTiles"
echo "   ./scripts/r2_sync.sh projects/$PROJECT/data/ $PROJECT/  # GeoParquet"
echo ""
echo "4. CONFIGURE FRONTEND LAYERS"
echo "   → Edit: projects/$PROJECT/layers.ts"
echo "   → Copy entries to: frontend/src/lib/config/layers.ts"
echo "   → Update PUBLIC_R2_URL in Vercel environment variables"
echo ""
echo "5. KEEP SUPABASE ALIVE"
echo "   → GitHub → Settings → Secrets → Add SUPABASE_DATABASE_URL"
echo "   → .github/workflows/keep-supabase-alive.yml runs Mon + Thu automatically"
echo ""
echo "Total monthly cost: \$0"
