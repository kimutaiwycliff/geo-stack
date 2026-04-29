# geo-stack

A reusable, production-ready geospatial backend + frontend stack for projects ranging
from national land administration platforms to climate risk dashboards.

One codebase. Three deployment modes. Switch between them by changing only env vars
and which Docker Compose override file you use — no code changes.

---

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Transactional spatial DB | PostGIS 17 (PostgreSQL 17 + PostGIS 3.5) | Write-heavy, KNN queries, audit log |
| Analytical compute | DuckDB 1.x + spatial extension | Embedded in FastAPI, queries GeoParquet |
| Live vector tiles | Martin (Rust, MVT) | Tiles from PostGIS at ~1ms/tile |
| Static vector tiles | PMTiles | Pre-generated, served from R2 |
| Raster tiles | TiTiler | COG files from disk or R2 |
| Spatial API | FastAPI + Python 3.12 | GeoJSON, STAC, tile proxy |
| Frontend | SvelteKit + MapLibre GL JS | Layer control, popups, legend, zoom-to |
| Reverse proxy | Caddy | Auto HTTPS in production |
| Orchestration | Docker Compose profiles | One file, three modes |

**Architecture**: PostGIS owns writes and KNN-heavy queries. DuckDB+GeoParquet owns
analytics and open-data queries. Both feed the same frontend via different serve paths.

---

## Deployment modes

### Mode 1 — Local development (Apple M1)

Full stack on your laptop via Docker Compose. No cloud accounts needed.

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.local.yml up
```

→ **[Full guide: docs/local-dev.md](docs/local-dev.md)**

### Mode 2 — Cloud-free ($0/month)

PostGIS on Supabase · Martin + FastAPI + TiTiler on Render · Data on Cloudflare R2 · Frontend on Vercel.

```bash
cp .env.cloud.example .env.cloud
# Fill in credentials, then test locally:
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up
```

→ **[Full guide: HOSTING.md](HOSTING.md)**

### Mode 3 — Production VPS (~€6/month)

Full stack on a single Hetzner CX21 (2 vCPU, 4 GB RAM). Caddy handles HTTPS automatically.

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

→ **[Full guide: docs/production-vps.md](docs/production-vps.md)**

---

## Prerequisites

| Tool | Install | Used for |
|------|---------|---------|
| Docker Desktop | [docker.com](https://docker.com) | All modes |
| Docker Compose v2 | Bundled with Docker Desktop | Orchestration |
| tippecanoe | `brew install tippecanoe` | Generating PMTiles |
| pmtiles CLI | `brew install protomaps/homebrew-protomaps/go-pmtiles` | Inspecting PMTiles |
| duckdb CLI | `brew install duckdb` | Data pipeline scripts |
| GDAL | `brew install gdal` | Loading data into PostGIS |
| Python 3.12+ | `brew install python` | Data pipeline scripts |

---

## Starting a new project

```bash
./scripts/new_project.sh <project-name>
# Creates projects/<name>/ with SQL files, .env stub, and layer config stub.
# Prints step-by-step instructions for Supabase + R2 setup.
```

Manual steps:

1. **Load your data** — vector data into PostGIS (for live MVT tiles) or GeoParquet (for analytics):
   ```bash
   ./scripts/load_postgis.sh input.gpkg geo.project_layer
   python scripts/to_geoparquet.py input.shp data/project_layer.parquet
   ```

2. **Restart Martin** after loading new PostGIS tables so it discovers them:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin
   ```

3. **Get the sourceLayer name** — Martin names vector layers `schema.table`:
   ```bash
   curl -s http://localhost:3000/geo.project_layer | python3 -m json.tool | grep '"id"'
   # "id": "geo.project_layer"   ← use this as sourceLayer in layers.ts
   ```

4. **Get bounds** for the zoom-to button:
   ```bash
   curl -s http://localhost:3000/geo.project_layer | python3 -m json.tool | grep bounds
   # or: ogrinfo -al -so input.shp
   ```

5. **Add layer** to `frontend/src/lib/config/layers.ts`:
   ```typescript
   {
     id: 'project-layer',
     label: 'My Layer',
     type: 'mvt',
     url: `${MARTIN_URL}/geo.project_layer/{z}/{x}/{y}`,
     sourceLayer: 'geo.project_layer',   // must match Martin's vector layer id
     paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.4 },
     visible: true,
     popupFields: ['name'],
     bounds: [33.91, -4.72, 41.90, 4.62],
   }
   ```

6. **Generate static tiles** (if using pmtiles):
   ```bash
   ./scripts/to_pmtiles.sh data/project_layer.parquet data/pmtiles/project_layer.pmtiles
   ./scripts/r2_sync.sh data/pmtiles/
   ```

---

## Layer type decision guide

| Situation | Type | Served by |
|-----------|------|-----------|
| Data changes daily, needs KNN/joins | `mvt` | Martin → PostGIS |
| Data rarely changes, want zero server cost | `pmtiles` | R2 (browser direct) |
| Needs server-side filtering or aggregation | `geojson` | FastAPI + DuckDB |
| Raster imagery, DEM, climate grids | `raster` | TiTiler → COG on R2 |

---

## Scripts reference

→ **[Full reference: scripts/README.md](scripts/README.md)** — includes bounds-finding guide.

```bash
python scripts/to_geoparquet.py input.shp data/layer.parquet
./scripts/to_pmtiles.sh data/layer.parquet data/pmtiles/layer.pmtiles
./scripts/load_postgis.sh data/layer.parquet geo.my_table
./scripts/r2_sync.sh data/pmtiles/
python scripts/overture_extract.py --bbox "36.65,-1.44,37.10,-1.16" --theme divisions
```

---

## Real-world test datasets

Two large, freely available Kenya datasets to validate your stack end-to-end.
No login required.

### Kenya roads — Shapefile, ~500k features, updates daily

```bash
curl -L -o /tmp/kenya-osm.zip \
  "https://download.geofabrik.de/africa/kenya-latest-free.shp.zip"
unzip /tmp/kenya-osm.zip "gis_osm_roads_free_1.*" -d /tmp/kenya-osm/

ogr2ogr -f PostgreSQL \
  "PG:host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  /tmp/kenya-osm/gis_osm_roads_free_1.shp \
  -nln geo.kenya_roads -lco GEOMETRY_NAME=geom -lco FID=id -t_srs EPSG:4326 -progress

docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin
curl -s http://localhost:3000/geo.kenya_roads | python3 -m json.tool | grep bounds
```

```typescript
// layers.ts entry
{
  id: 'kenya-roads', label: 'Kenya Roads (OSM)', type: 'mvt',
  url: `${MARTIN_URL}/geo.kenya_roads/{z}/{x}/{y}`,
  sourceLayer: 'geo.kenya_roads',
  paint: {
    'line-color': ['match', ['get', 'fclass'],
      'motorway', '#ef4444', 'trunk', '#f97316', 'primary', '#f59e0b',
      'secondary', '#84cc16', '#d1d5db'],
    'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.5, 14, 3],
  },
  minzoom: 5, maxzoom: 18, visible: true,
  popupFields: ['name', 'fclass', 'ref', 'maxspeed'],
  bounds: [33.91, -4.73, 42.08, 5.28],
}
```

### Kenya admin boundaries — GeoPackage, all 5 admin levels

```bash
curl -L -o /tmp/gadm41_KEN.gpkg \
  "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_KEN.gpkg"

ogrinfo /tmp/gadm41_KEN.gpkg   # list all layers

ogr2ogr -f PostgreSQL \
  "PG:host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  /tmp/gadm41_KEN.gpkg "ADM_ADM_1" \
  -nln geo.kenya_counties -lco GEOMETRY_NAME=geom -lco FID=id -t_srs EPSG:4326

docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin
```

---

## PostGIS vs DuckDB: when to use which

| Criteria | PostGIS | DuckDB + GeoParquet |
|----------|---------|---------------------|
| Data changes | Daily or more often | Weekly, monthly, or static |
| Write operations | Yes | No (read-only) |
| KNN / nearest neighbour | Yes (PostGIS index, accurate) | Limited |
| Joins with other tables | Yes (SQL joins) | Yes (parquet files) |
| Audit trail / history | Yes (audit schema) | No |
| Dataset size | City scale (millions of rows) | Country/global scale (billions) |
| Query type | Specific features by ID/location | Aggregations, summaries, stats |
| Setup cost | Running container needed | Zero (embedded in Python) |
| Open data integration | Requires ETL | Direct read from S3/R2 |
