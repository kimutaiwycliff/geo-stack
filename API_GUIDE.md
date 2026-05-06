# geo-stack API Guide

A practical reference for querying data, running DuckDB analytics, and understanding every endpoint across all three deployment modes.

---

## Base URLs by deployment mode

The stack runs in three modes. Every curl example below uses `$API` — substitute the URL for your mode.

### Mode 1 — Local dev (Docker Compose on M1)

```bash
export API=http://localhost:8000
export MARTIN=http://localhost:3000
export TITILER=http://localhost:8080
export FRONTEND=http://localhost:5173
```

Start with:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up
```

PostGIS is also directly reachable at `localhost:5432` for QGIS, DBeaver, or psql.

---

### Mode 2 — Cloud-free (Supabase + Render + Vercel)

| Service    | Host                                    |
|------------|-----------------------------------------|
| API        | `https://<your-api>.onrender.com`       |
| Martin     | `https://<your-martin>.onrender.com`    |
| TiTiler    | `https://<your-titiler>.onrender.com`   |
| Frontend   | `https://<your-project>.vercel.app`     |
| PostGIS    | Supabase — no direct port (pooler only) |
| Files      | Cloudflare R2 (via `R2_PUBLIC_URL`)     |

```bash
export API=https://geo-api-xxxx.onrender.com
export MARTIN=https://geo-martin-xxxx.onrender.com
export TITILER=https://geo-titiler-xxxx.onrender.com
```

Set these in Render's environment variables panel and in Vercel's project settings. See `HOSTING.md` for full walkthrough.

---

### Mode 3 — Production VPS (Caddy + single server)

All services sit behind Caddy at one domain with auto-HTTPS (Let's Encrypt). Caddy routes by path prefix:

| Path prefix  | Routes to         | Internal URL            |
|--------------|-------------------|-------------------------|
| `/api`       | FastAPI            | `http://api:8000`       |
| `/tiles`     | Martin             | `http://martin:3000`    |
| `/raster`    | TiTiler            | `http://titiler:80`     |
| `/` (root)   | SvelteKit frontend | `http://frontend:3001`  |

```bash
export DOMAIN=geo.yourdomain.com

export API=https://$DOMAIN/api
export MARTIN=https://$DOMAIN/tiles
export TITILER=https://$DOMAIN/raster
export FRONTEND=https://$DOMAIN
```

Start with:
```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

`DOMAIN` and `ACME_EMAIL` must be set in `.env.production`. DNS A record must point to your server IP before first start.

---

## Mental model: three data paths

```
Browser / curl
      │
      ├── $API/features/{layer}      → PostGIS (asyncpg) → GeoJSON
      │                                  Live data, bbox filter
      │
      ├── $API/analytics/parquet     → DuckDB (embedded) → GeoJSON
      │                                  Analytics on GeoParquet files
      │
      └── $API/tiles/...             → Martin MVT proxy
                                         or PMTiles direct from R2 (no API call)
```

PostGIS owns **writes and KNN queries**. DuckDB owns **analytics reads** on GeoParquet. Martin serves **live vector tiles** from the `geo` schema. PMTiles are static files served with HTTP range requests — no server involved.

---

## 1. GeoJSON from PostGIS — `/features/{layer}`

The simplest path. PostGIS runs the spatial query; the API returns a GeoJSON FeatureCollection.

### Allowed layers

| Layer name           | PostGIS table                  | Notes                   |
|----------------------|-------------------------------|-------------------------|
| `parcels`            | `geo.parcels`                 | Land parcels            |
| `boundaries`         | `geo.boundaries`              | Admin boundaries        |
| `points_of_interest` | `geo.points_of_interest`      | POI with category field |

> **Adding a new layer**: edit `api/routers/features.py:ALLOWED_LAYERS`. The allowlist is the security boundary — never build the table name from user input.

### Parameters

| Param   | Type    | Default | Description                             |
|---------|---------|---------|-----------------------------------------|
| `bbox`  | string  | —       | `xmin,ymin,xmax,ymax` in EPSG:4326     |
| `limit` | integer | 500     | Max features returned. Hard cap: 5000   |

### Examples

```bash
# All POIs (up to 500)
curl $API/features/points_of_interest

# Nairobi metro bbox
curl "$API/features/points_of_interest?bbox=36.65,-1.44,37.10,-1.16&limit=2000"

# County boundaries
curl $API/features/boundaries

# Parcels in a small area
curl "$API/features/parcels?bbox=36.80,-1.30,36.85,-1.25&limit=100"
```

**Mode-specific:**

```bash
# Local
curl "http://localhost:8000/features/points_of_interest?bbox=36.65,-1.44,37.10,-1.16"

# Render (cloud-free)
curl "https://geo-api-xxxx.onrender.com/features/points_of_interest?bbox=36.65,-1.44,37.10,-1.16"

# VPS (behind Caddy at /api)
curl "https://geo.yourdomain.com/api/features/points_of_interest?bbox=36.65,-1.44,37.10,-1.16"
```

### How the SQL works

```sql
-- Built internally in features.py:66-78
SELECT
    jsonb_build_object(
        'type', 'Feature',
        'id', id,
        'geometry', ST_AsGeoJSON(geom)::jsonb,
        'properties', (to_jsonb(t.*) - 'geom' - 'id')
    ) AS feature
FROM geo.points_of_interest t
WHERE geom && ST_MakeEnvelope(36.65, -1.44, 37.10, -1.16, 4326)
ORDER BY id
LIMIT 500;
```

The `&&` operator uses the GIST index for a fast bounding-box pre-filter. Geometry is already in EPSG:4326 — no reprojection.

### Using the POI layer in layers.ts

```typescript
// The config you already have is correct:
{
  id: 'poi',
  label: 'Points of Interest',
  type: 'geojson',
  url: `${API_URL}/features/points_of_interest`,
  // API_URL comes from PUBLIC_API_URL env var — set per mode (see base URLs above)
}
```

`PUBLIC_API_URL` in `.env` / Vercel / docker-compose drives this. It resolves at build time so the right URL bakes into each deployment.

**To filter to the current map viewport as the user pans:**

```typescript
map.on('moveend', () => {
  const b = map.getBounds();
  const bbox = `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
  map.getSource('poi')?.setData(
    `${API_URL}/features/points_of_interest?bbox=${bbox}&limit=2000`
  );
});
```

---

## 2. DuckDB analytics — `/analytics/parquet`

DuckDB is embedded in the FastAPI process — no separate server in any mode. It reads GeoParquet files from the `/data` volume or directly from R2 via the `httpfs` extension.

**Why DuckDB for analytics?** Columnar storage and Parquet row-group pruning. A bbox query on a Hilbert-sorted 10M-feature file reads less than 1% of disk — orders of magnitude faster than PostGIS for read-only analytics.

### Query a GeoParquet file

```
GET /analytics/parquet?file=<filename>&bbox=<bbox>&limit=<n>
```

| Param   | Required | Description                                              |
|---------|----------|----------------------------------------------------------|
| `file`  | yes      | Filename in `/data`, or full `s3://bucket/key` for R2   |
| `bbox`  | no       | `xmin,ymin,xmax,ymax` (EPSG:4326)                       |
| `limit` | no       | Default 500, max 10000                                   |

```bash
# Local — file mounted in ./data → /data inside container
curl "http://localhost:8000/analytics/parquet?file=kenya_admin.parquet"
curl "http://localhost:8000/analytics/parquet?file=kenya_admin.parquet&bbox=36.65,-1.44,37.10,-1.16&limit=200"

# Render (cloud-free) — file is in R2, DuckDB reads it via httpfs
curl "https://geo-api-xxxx.onrender.com/analytics/parquet?file=s3://geo-parquet/staging/kenya_admin/abc12345.parquet"

# VPS (Caddy routes /api → FastAPI)
curl "https://geo.yourdomain.com/api/analytics/parquet?file=kenya_admin.parquet"
```

Returns a GeoJSON FeatureCollection.

### Layer summary statistics

```bash
# Local
curl "http://localhost:8000/analytics/summary/kenya_admin"

# Render
curl "https://geo-api-xxxx.onrender.com/analytics/summary/kenya_admin"

# VPS
curl "https://geo.yourdomain.com/api/analytics/summary/kenya_admin"
```

```json
{
  "layer": "kenya_admin",
  "total_features": 47,
  "geometry_types": { "MULTIPOLYGON": 47 },
  "bbox_filter": null
}
```

---

## 3. DuckDB — direct queries (outside the API)

Query GeoParquet files directly from Python or the CLI — useful for exploration and scripting without going through the API.

### Python

```python
import duckdb

con = duckdb.connect(":memory:")
con.execute("INSTALL spatial; LOAD spatial;")

# Local file
result = con.execute("""
    SELECT
        name_1,
        ST_Area(geometry) AS area_deg2,
        ST_AsText(ST_Centroid(geometry)) AS centroid
    FROM read_parquet('data/geo-parquet/kenya_admin.parquet')
    LIMIT 5
""").fetchdf()
print(result)

# Spatial join — which county is this point in?
con.execute("""
    SELECT name_1
    FROM read_parquet('data/geo-parquet/kenya_admin.parquet')
    WHERE ST_Contains(geometry, ST_Point(36.82, -1.29))
""").fetchdf()

# Count POIs per county
con.execute("""
    SELECT a.name_1, COUNT(*) AS poi_count
    FROM read_parquet('data/geo-parquet/kenya_admin.parquet') a
    JOIN read_parquet('data/geo-parquet/poi.parquet') p
      ON ST_Contains(a.geometry, p.geometry)
    GROUP BY a.name_1
    ORDER BY poi_count DESC
""").fetchdf()
```

### Reading from R2 directly (cloud / production)

```python
con = duckdb.connect(":memory:")
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.execute("""
    SET s3_endpoint = '<account_id>.r2.cloudflarestorage.com';
    SET s3_access_key_id = 'your_key';
    SET s3_secret_access_key = 'your_secret';
    SET s3_region = 'auto';
    SET s3_url_style = 'path';
""")

# Read the file the API also reads — same data, no API overhead
con.execute("""
    SELECT name_1, ST_AsText(ST_Centroid(geometry)) AS centroid
    FROM read_parquet('s3://geo-parquet/staging/kenya_admin/abc12345.parquet')
    LIMIT 10
""").fetchdf()
```

Credentials come from your `.env` / `.env.production` — same values as `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_ENDPOINT`.

---

## 4. Vector tiles — MVT and PMTiles

### MVT — live tiles via Martin

Martin reads PostGIS `geo` schema and serves MVT tiles. The API proxies at `/tiles/` (Mode 1 & 2) so the frontend only needs one base URL. In Mode 3 (VPS), Caddy routes `/tiles` directly to Martin for zero overhead.

```
GET /tiles/{source}/{z}/{x}/{y}.mvt
```

`{source}` is always the Martin source ID: `schema.table`.

```bash
# Local
curl "http://localhost:8000/tiles/geo.adm_adm_1/6/38/32.mvt"
# or directly to Martin (bypasses the API proxy)
curl "http://localhost:3000/geo.adm_adm_1/6/38/32"

# Render (cloud-free)
curl "https://geo-api-xxxx.onrender.com/tiles/geo.adm_adm_1/6/38/32.mvt"
# or Martin directly
curl "https://geo-martin-xxxx.onrender.com/geo.adm_adm_1/6/38/32"

# VPS (Caddy routes /tiles → Martin directly — no FastAPI in the path)
curl "https://geo.yourdomain.com/tiles/geo.adm_adm_1/6/38/32"
```

**In layers.ts** — the URL uses `MARTIN_URL`, not `API_URL`, so it talks to Martin directly:

```typescript
{
  id: 'boundaries',
  type: 'mvt',
  url: `${MARTIN_URL}/geo.adm_adm_1/{z}/{x}/{y}`,
  sourceLayer: 'geo.adm_adm_1',
  // MARTIN_URL = PUBLIC_MARTIN_URL env var:
  //   Local:   http://localhost:3000
  //   Render:  https://geo-martin-xxxx.onrender.com
  //   VPS:     https://geo.yourdomain.com/tiles
}
```

**Verify your source layer name:**

```bash
curl http://localhost:3000/geo.adm_adm_1 | python3 -m json.tool | grep '"id"'
# Martin names the vector layer "geo.adm_adm_1" — that's what goes in sourceLayer
```

**When to use MVT**: data changes frequently, very large datasets (millions of features), server-side auth needed.

---

### PMTiles — static tiles from R2

PMTiles is a single-file tile archive. The browser downloads only the tiles it needs via HTTP range requests. No tile server is involved — MapLibre fetches directly from R2's public URL.

```typescript
// In layers.ts — no API or Martin involved
{
  id: 'nairobi-wards',
  type: 'pmtiles',
  // Local dev: served from ./data/pmtiles/ via the Docker volume
  url: '/data/pmtiles/nairobi_wards.pmtiles',
  // Cloud / production: public R2 URL
  // url: 'https://pub-xxxx.r2.dev/nairobi_wards.pmtiles',
  sourceLayer: 'nairobi_wards',
}
```

**Generate PMTiles from a GeoParquet file:**

```bash
# Wraps tippecanoe + pmtiles convert
./scripts/to_pmtiles.sh data/geo-parquet/nairobi_wards.parquet data/pmtiles/nairobi_wards.pmtiles

# Upload to R2
./scripts/r2_sync.sh data/pmtiles/
```

**There is no API query endpoint for PMTiles** — MapLibre reads the file directly. For analytics on the same data, run DuckDB against the source GeoParquet via `/analytics/parquet`.

**When to use PMTiles**: data changes rarely, zero server cost, offline support needed.

---

## 5. STAC catalog — `/stac/*`

STAC is a standard for discovering geospatial assets. The catalog scans `/data` at request time.

```bash
# List all collections (subdirectories with .parquet files)
# Local
curl http://localhost:8000/stac/collections

# Render
curl https://geo-api-xxxx.onrender.com/stac/collections

# VPS
curl https://geo.yourdomain.com/api/stac/collections

# List items in a collection
curl $API/stac/collections/geo-parquet/items
```

When `R2_PUBLIC_URL` is set, asset hrefs point directly to R2 (no API in the download path).

---

## 6. Ingest pipeline — `/ingest/*`

For loading new data into the stack from any client — curl, Postman, or the built-in frontend UI.

### Step 1 — Upload a file

```bash
# Local
curl -X POST http://localhost:8000/ingest/upload \
  -F "file=@kenya_admin.gpkg"

# Render
curl -X POST https://geo-api-xxxx.onrender.com/ingest/upload \
  -F "file=@kenya_admin.gpkg"

# VPS
curl -X POST https://geo.yourdomain.com/api/ingest/upload \
  -F "file=@kenya_admin.gpkg"

# Returns:
# { "job_id": "abc...", "file_name": "kenya_admin.gpkg", "layers": [...] }
```

Supported formats: GeoJSON, GeoPackage, Shapefile (ZIP), KML, GeoParquet — anything ogr2ogr reads.

### Step 2 — Process (import to PostGIS)

```bash
curl -X POST $API/ingest/process \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "abc...",
    "layers": [
      {
        "source_layer": "kenya_admin",
        "target_table": "staging.kenya_admin",
        "overwrite": true,
        "export_parquet": true
      }
    ]
  }'
# Returns: { "job_ids": ["abc..."] }
```

`export_parquet: true` triggers a GeoParquet export to R2 after import. Requires `R2_*` env vars.

### Step 3 — Poll progress

```bash
# Single job — SSE stream
curl $API/ingest/job/abc...
# data: {"status": "processing", "pct": 42, "rows_inserted": 0, "error": null}
# data: {"status": "done", "pct": 100, "rows_inserted": 47, "error": null}

# Multiple jobs at once
curl "$API/ingest/batch?ids=abc...,def..."
```

### Other ingest endpoints

```bash
# List recent jobs (last 50)
curl $API/ingest/jobs

# List jobs that produced a GeoParquet export (with R2 URLs)
curl $API/ingest/parquet

# Delete a job and its R2 backup
curl -X DELETE $API/ingest/job/abc...
```

---

## 7. Health check

```bash
curl $API/health
# {"status": "ok", "duckdb": true, "postgis": true, ...}
```

Useful in CI or uptime monitors — returns HTTP 200 only when both DuckDB spatial and PostGIS pool are ready.

---

## 8. Interactive API explorer (Swagger / ReDoc)

Auto-generated docs are available when `SHOW_DOCS=true` (default in local and cloud modes; disabled by default in production VPS):

| Mode         | Swagger UI                                          | ReDoc                                                |
|--------------|-----------------------------------------------------|------------------------------------------------------|
| Local        | http://localhost:8000/docs                          | http://localhost:8000/redoc                          |
| Render       | https://geo-api-xxxx.onrender.com/docs              | https://geo-api-xxxx.onrender.com/redoc              |
| VPS          | https://geo.yourdomain.com/api/docs *(if enabled)*  | https://geo.yourdomain.com/api/redoc *(if enabled)*  |

To enable docs on VPS: set `SHOW_DOCS=true` in `.env.production`. Keep it off in publicly accessible production deployments.

---

## 9. Query decision guide

| You want to...                               | Use                                              |
|----------------------------------------------|--------------------------------------------------|
| Show live data on a map                      | `type: 'mvt'` in layers.ts → Martin             |
| Show static boundaries (rarely changing)     | `type: 'pmtiles'` in layers.ts → R2             |
| Fetch features with filters for a UI widget  | `GET $API/features/{layer}?bbox=...`            |
| Run spatial analytics on a large dataset     | `GET $API/analytics/parquet?file=...`           |
| Ad-hoc exploration in Python / notebook      | DuckDB Python directly on `.parquet` files      |
| Load new data into PostGIS                   | `POST $API/ingest/upload` → `POST $API/ingest/process` |
| Discover what GeoParquet data is available   | `GET $API/stac/collections`                     |

---

## 10. Environment variables reference

Set these in `.env.local` (Mode 1), Render env panel (Mode 2), or `.env.production` (Mode 3).

| Variable              | Default                 | Mode | Used by                        |
|-----------------------|-------------------------|------|-------------------------------|
| `DATABASE_URL`        | required                | all  | PostGIS asyncpg pool           |
| `SUPABASE_DIRECT_URL` | —                       | 2    | ogr2ogr bulk load (port 5432) |
| `ENV`                 | `local`                 | all  | `local` / `cloud` / `production` |
| `SHOW_DOCS`           | `true`                  | all  | Swagger/ReDoc visibility       |
| `MARTIN_URL`          | `http://martin:3000`    | all  | Tile proxy (internal Docker)   |
| `DATA_DIR`            | `/data`                 | all  | DuckDB, STAC scan              |
| `R2_ENDPOINT`         | —                       | 2,3  | DuckDB httpfs, ingest upload   |
| `R2_ACCESS_KEY`       | —                       | 2,3  | DuckDB httpfs, ingest upload   |
| `R2_SECRET_KEY`       | —                       | 2,3  | DuckDB httpfs, ingest upload   |
| `R2_PUBLIC_URL`       | —                       | 2,3  | STAC asset hrefs, parquet URLs |
| `R2_PARQUET_BUCKET`   | `geo-parquet`           | 2,3  | Parquet export destination     |
| `R2_UPLOADS_BUCKET`   | `geo-uploads`           | 2,3  | Ingest file backup             |
| `DUCKDB_THREADS`      | `4`                     | all  | DuckDB parallelism             |
| `DUCKDB_MEMORY`       | `512MB`                 | all  | DuckDB memory cap              |
| `API_RATE_LIMIT`      | `100`                   | all  | Requests/minute per IP         |
| `DOMAIN`              | required in Mode 3      | 3    | Caddy TLS + routing            |
| `ACME_EMAIL`          | required in Mode 3      | 3    | Let's Encrypt registration     |
| `PUBLIC_API_URL`      | `http://localhost:8000` | all  | SvelteKit → API URL            |
| `PUBLIC_MARTIN_URL`   | `http://localhost:3000` | all  | SvelteKit → Martin URL         |
| `PUBLIC_TITILER_URL`  | `http://localhost:8080` | all  | SvelteKit → TiTiler URL        |
