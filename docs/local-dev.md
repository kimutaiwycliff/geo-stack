# Mode 1 — Local Development (Apple M1)

Docker Compose runs the full stack on your laptop. No cloud accounts needed.

---

## Prerequisites

| Tool | Install | Used for |
|------|---------|---------|
| Docker Desktop | [docker.com](https://docker.com) | All containers |
| Docker Compose v2 | Bundled with Docker Desktop | Orchestration |
| tippecanoe | `brew install tippecanoe` | Generating PMTiles |
| pmtiles CLI | `brew install protomaps/homebrew-protomaps/go-pmtiles` | Inspecting PMTiles |
| duckdb CLI | `brew install duckdb` | Data pipeline scripts |
| GDAL (`ogr2ogr`) | `brew install gdal` | Loading data into PostGIS |
| Python 3.12+ | `brew install python` | Data pipeline scripts |

---

## Quickstart

```bash
git clone https://github.com/youruser/geo-stack
cd geo-stack
```

The repo ships a ready `.env` with safe dev defaults. You can start immediately:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up
```

> **Important**: Docker Compose auto-loads `.env` from the project root, **not** `.env.local`.
> If you deleted it: `cp .env.example .env`

First run pulls ~1.5 GB of images and builds the API and frontend — allow 60–90 seconds
for PostGIS to initialise and run the SQL init scripts.

### Services

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:5173 | MapLibre map, HMR enabled |
| API docs | http://localhost:8000/docs | FastAPI Swagger UI |
| Martin catalog | http://localhost:3000/catalog | Vector tile sources |
| TiTiler | http://localhost:8080 | Raster tile server |
| PostGIS | localhost:5432 | Connect with QGIS or DBeaver |

### Verify health

```bash
curl http://localhost:8000/health
# → {"status":"ok","postgis":true,"duckdb":true}

docker compose -f docker-compose.yml -f docker-compose.local.yml ps
# All five containers should show (healthy)
```

### Credentials (local dev)

```
Host:     localhost
Port:     5432
Database: geodata
User:     geouser
Password: geostack_dev
```

---

## Loading data

### Shapefile or GeoJSON → PostGIS (MVT layers)

```bash
ogr2ogr \
  -f PostgreSQL \
  "PG:host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  input.shp \
  -nln geo.my_layer \
  -lco GEOMETRY_NAME=geom \
  -lco FID=id \
  -t_srs EPSG:4326 \
  -progress
```

### GeoPackage → PostGIS (list layers first)

```bash
# See all layers in the file
ogrinfo input.gpkg

# Load a specific layer
ogr2ogr \
  -f PostgreSQL \
  "PG:host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  input.gpkg \
  "LayerName" \
  -nln geo.my_layer \
  -lco GEOMETRY_NAME=geom \
  -lco FID=id \
  -t_srs EPSG:4326
```

### Any format → GeoParquet (DuckDB/analytics layers)

```bash
python scripts/to_geoparquet.py input.shp data/my_layer.parquet
python scripts/to_geoparquet.py input.geojson data/my_layer.parquet --bbox "36.5,-1.5,37.2,-0.5"
```

### GeoParquet → PMTiles (static layers, no tile server)

```bash
./scripts/to_pmtiles.sh data/my_layer.parquet data/pmtiles/my_layer.pmtiles --max-zoom 16
```

---

## Restart Martin after loading new tables

**Martin discovers PostGIS tables only at startup.** If you load a table into PostGIS
after Martin is already running, it will return 404 for that source until you restart it.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin

# Then verify the new table is published:
curl -s http://localhost:3000/geo.my_layer | python3 -m json.tool | grep '"id"'
# "id": "geo.my_layer"
```

This applies every time you add a new table. Existing tables are not affected — only
the newly added one needs a restart to become visible.

---

## Finding bounds for a layer

Every layer in `layers.ts` can have `bounds: [west, south, east, north]` for the
zoom-to button. You never need to calculate this manually.

### MVT layers — ask Martin

After restarting Martin, its TileJSON endpoint includes the exact bounds:

```bash
curl -s http://localhost:3000/geo.my_layer | python3 -m json.tool | grep bounds
# "bounds": [33.909821, -4.720017, 41.899578, 4.622525]
```

Copy those four numbers directly into `layers.ts` as `bounds: [33.91, -4.72, 41.90, 4.62]`.

### Any file — ogrinfo (fastest)

```bash
ogrinfo -al -so input.shp
ogrinfo -al -so input.gpkg LayerName
# Extent: (west, south) - (east, north)
```

### GeoParquet or GeoJSON — DuckDB

```bash
duckdb -c "
  LOAD spatial;
  SELECT
    ST_XMin(ST_Extent(geom)) AS west, ST_YMin(ST_Extent(geom)) AS south,
    ST_XMax(ST_Extent(geom)) AS east, ST_YMax(ST_Extent(geom)) AS north
  FROM read_parquet('data/my_layer.parquet');
"
```

### PMTiles files

```bash
pmtiles show data/pmtiles/my_layer.pmtiles
# bounds: west,south,east,north
```

### PostGIS (after loading)

```sql
SELECT
  ST_XMin(ST_Extent(geom)) AS west, ST_YMin(ST_Extent(geom)) AS south,
  ST_XMax(ST_Extent(geom)) AS east, ST_YMax(ST_Extent(geom)) AS north
FROM geo.my_layer;

-- For large tables, use the statistics estimate (instant):
SELECT ST_EstimatedExtent('geo', 'my_layer', 'geom');
```

---

## Adding a layer to the frontend

After loading data and getting bounds, add an entry to
`frontend/src/lib/config/layers.ts`. The file auto-reloads via Vite HMR — no
container restart needed.

**Critical**: For MVT layers, `sourceLayer` must be the full `schema.table` form.
Martin names the vector layer inside each tile `"geo.my_layer"` — not `"my_layer"`.
Confirm it:

```bash
curl -s http://localhost:3000/geo.my_layer | python3 -m json.tool | grep '"id"'
# "id": "geo.my_layer"   ← use this exact string as sourceLayer
```

```typescript
// MVT layer from Martin
{
  id: 'my-layer',
  label: 'My Layer',
  type: 'mvt',
  url: `${MARTIN_URL}/geo.my_layer/{z}/{x}/{y}`,
  sourceLayer: 'geo.my_layer',   // must match Martin's vector layer id
  paint: { 'line-color': '#ef4444', 'line-width': 2 },
  minzoom: 6,
  maxzoom: 18,
  visible: true,
  popupFields: ['name', 'category'],
  bounds: [33.91, -4.72, 41.90, 4.62],
},

// PMTiles layer (static)
{
  id: 'my-static-layer',
  label: 'My Static Layer',
  type: 'pmtiles',
  url: '/data/pmtiles/my_layer.pmtiles',   // served from ./data/pmtiles/ mount
  sourceLayer: 'my_layer',                  // matches tippecanoe layer name
  paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.2 },
  visible: false,
  popupFields: ['name'],
  bounds: [36.65, -1.44, 37.10, -1.16],
},
```

---

## Hot reload behaviour

| What you change | Reloads automatically? |
|----------------|----------------------|
| `frontend/src/` — any Svelte/TS file | Yes — Vite HMR, instant |
| `api/` — any Python file | Yes — uvicorn `--reload` |
| `martin/config.yaml` | No — `restart martin` |
| New PostGIS table | No — `restart martin` |
| `docker-compose.local.yml` | No — `down && up` |

---

## Useful one-liners

```bash
# Tail all container logs
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f

# Tail one service
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f api

# Restart a single service
docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin

# Stop everything, remove orphan containers
docker compose -f docker-compose.yml -f docker-compose.local.yml down --remove-orphans

# Connect to PostGIS with psql
psql "host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev"

# List all tables in geo schema
psql "host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  -c "\dt geo.*"

# Row counts for all tables
psql "host=localhost port=5432 dbname=geodata user=geouser password=geostack_dev" \
  -c "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables WHERE schemaname='geo' ORDER BY n_live_tup DESC;"
```

---

## Troubleshooting

**`POSTGRES_PASSWORD is required` on startup**
Docker Compose loads `.env`, not `.env.local`. The repo ships `.env` with a working
default. If you deleted it: `cp .env.example .env`

**Apple M1: `no matching manifest for linux/arm64`**
PostGIS 17-3.5, Martin, and TiTiler only publish `linux/amd64` images. The fix is
`platform: linux/amd64` (not `linux/arm64`) — arm64 images don't exist for these.
All three are already set correctly in `docker-compose.local.yml`.

**TiTiler unhealthy / port 8080 connection refused**
TiTiler's gunicorn binds to port **80** inside the container, not 8080. Port mapping
must be `"8080:80"` and health check must use `http://127.0.0.1:80/healthz`.
Both are set correctly in the provided config.

**Service health checks `unhealthy` despite the process running**
Alpine Linux resolves `localhost` to `::1` (IPv6), but services bind to `0.0.0.0`
(IPv4). Health checks must use `http://127.0.0.1:PORT` — not `http://localhost:PORT`.

**Martin 404 for a table you just loaded**
Martin discovers tables at startup only. Restart it:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml restart martin
```

**Martin layer renders nothing / invisible features**
The `sourceLayer` in `layers.ts` doesn't match Martin's vector layer name. Martin
uses `"geo.table_name"` (with schema prefix). Confirm:
```bash
curl -s http://localhost:3000/geo.my_table | python3 -m json.tool | grep '"id"'
```

**Stale containers blocking startup**
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down --remove-orphans
```

**Frontend Vite proxy `/api` calls fail**
Inside the container `PUBLIC_API_URL=http://localhost:8000` points to itself. The
env var `VITE_API_PROXY_TARGET: http://api:8000` in `docker-compose.local.yml`
tells Vite to use the Docker service name instead.

**`npm ci` fails with no lockfile**
The dev Dockerfile uses `npm install`. If you see lockfile errors you have an old
image — rebuild: `docker compose build frontend`
