# Mode 2 — Zero-Cost Cloud Hosting

PostGIS on Supabase · Martin + FastAPI + TiTiler on Render · Data on Cloudflare R2 · Frontend on Vercel.

**Total cost: $0/month per project** until you exceed the free tier limits listed at the bottom.

---

## Architecture

```
Browser
  │
  ├─→ Vercel            SvelteKit frontend (auto-deploy on git push)
  │     │
  │     ├─→ Render       FastAPI /features, /analytics, /stac, /ingest
  │     │     ├─→ Supabase  PostGIS writes (asyncpg, pooler port 6543)
  │     │     ├─→ Supabase  ogr2ogr bulk-load (direct port 5432, COPY mode)
  │     │     └─→ R2        DuckDB reads geo-parquet via httpfs
  │     │
  │     ├─→ Render       Martin MVT tiles (/geo/<table>/{z}/{x}/{y})
  │     │     └─→ Supabase  PostGIS (session pooler port 5432, geo schema only)
  │     │
  │     ├─→ Render       TiTiler raster tiles
  │     │     └─→ R2 geo-pmtiles  COG files via GDAL VSI S3
  │     │
  │     └─→ R2 geo-pmtiles   PMTiles (browser range-requests, no server)

Upload flow (any file size, any GDAL format):
  Browser → stream raw file → Render (FastAPI /ingest/upload)
                              ├─→ ogrinfo: detect layers
                              ├─→ R2 geo-uploads: durable backup
                              └─→ ogr2ogr: direct → Supabase staging
                                  ↑ progress via SSE (staging.ingest_jobs)

R2 buckets:
  geo-pmtiles   public   PMTiles + COGs  (browser range requests)
  geo-parquet   public   GeoParquet      (DuckDB httpfs analytics)
  geo-uploads   private  Raw uploads     (ogr2ogr staging, auto-cleaned)
```

---

## Section 1 — One-time setup

Do this once. All projects share the same Render services, R2 bucket, and Vercel team.

### 1.1 Cloudflare R2

**Why R2?** 10 GB free storage, 10 M reads/month, 1 M writes/month, and **zero egress fees**
(unlike AWS S3 which charges per GB downloaded). PMTiles and GeoParquet both rely on HTTP range
requests — no egress cost makes R2 the natural fit.

1. Create a Cloudflare account (free, no credit card needed).

2. Create **three buckets** (R2 → Create bucket):

   | Bucket | Location | Purpose |
   |--------|----------|---------|
   | `geo-pmtiles` | auto | PMTiles + COG rasters — **public** |
   | `geo-parquet` | auto | GeoParquet for DuckDB analytics — **public** |
   | `geo-uploads` | auto | Raw file uploads for server-side ingest — **private** |

3. Enable public access on `geo-pmtiles` and `geo-parquet`:
   R2 → bucket → Settings → Public access → Allow public.
   Each gives you a URL like `https://pub-<hash>.r2.dev`.
   Note both URLs — you will use the `geo-pmtiles` URL as `R2_PUBLIC_URL`.
   Leave `geo-uploads` **private** (no public access).

4. Apply CORS to `geo-pmtiles` so browsers can load PMTiles and COGs via range requests:
   ```bash
   npm install -g wrangler
   wrangler login
   wrangler r2 bucket cors put geo-pmtiles --file hosting/r2_cors.json
   ```
   The `Range` header in the CORS config is critical — both PMTiles and COG rely on
   HTTP range requests to fetch only the tile or chunk they need.

5. Create an API token (one token covers all three buckets):
   R2 → Manage R2 API Tokens → Create API Token.
   - Permissions: **Object Read & Write**
   - Scope: all three buckets (`geo-pmtiles`, `geo-parquet`, `geo-uploads`)
   - Copy `Access Key ID` and `Secret Access Key` — needed for `.env.cloud` and Render.

### 1.2 Render

1. Create a Render account (free, GitHub login).
2. Connect your GitHub repo: Render Dashboard → New → Blueprint → select this repo.
   Render reads `hosting/render.yaml` and creates three services:
   - `geo-martin` (Martin tile server)
   - `geo-api` (FastAPI)
   - `geo-titiler` (TiTiler)
3. Set environment variables on each service (Render Dashboard → service → Environment):

   **geo-martin**:
   | Variable | Value |
   |---------|-------|
   | `DATABASE_URL` | Supabase **session** pooler URL (port **5432**) — NOT port 6543. Martin uses prepared statements at startup and hangs on the transaction pooler. |

   **geo-api**:
   | Variable | Value |
   |---------|-------|
   | `DATABASE_URL` | Supabase **transaction** pooler URL (port **6543**) — for asyncpg |
   | `SUPABASE_DIRECT_URL` | Supabase **direct** URL (port **5432**) — for ogr2ogr COPY mode. Dashboard → Project Settings → Database → Connection string → URI (direct). Format: `postgresql://postgres:PASS@db.XXXX.supabase.co:5432/postgres` |
   | `R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
   | `R2_ACCESS_KEY` | Your R2 access key |
   | `R2_SECRET_KEY` | Your R2 secret key |
   | `R2_PMTILES_BUCKET` | `geo-pmtiles` |
   | `R2_PARQUET_BUCKET` | `geo-parquet` |
   | `R2_UPLOADS_BUCKET` | `geo-uploads` |
   | `R2_PUBLIC_URL` | Public URL of `geo-pmtiles` bucket (`https://pub-<hash>.r2.dev`) |
   | `CORS_ORIGINS` | Your Vercel frontend URL |

   **geo-titiler**:
   | Variable | Value |
   |---------|-------|
   | `AWS_ACCESS_KEY_ID` | Your R2 access key |
   | `AWS_SECRET_ACCESS_KEY` | Your R2 secret key |
   | `AWS_S3_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |

4. Note your Render service URLs — you need them for Vercel env vars:
   - `https://geo-api-<hash>.onrender.com`
   - `https://geo-martin-<hash>.onrender.com`
   - `https://geo-titiler-<hash>.onrender.com`

### 1.3 Vercel

1. Create a Vercel account (free, GitHub login).
2. New Project → Import from GitHub → select this repo → Framework: SvelteKit.
3. Root directory: `frontend`.
4. Set environment variables (Vercel → Project → Settings → Environment Variables):
   | Variable | Value |
   |---------|-------|
   | `PUBLIC_API_URL` | `https://geo-api-<hash>.onrender.com` |
   | `PUBLIC_MARTIN_URL` | `https://geo-martin-<hash>.onrender.com` |
   | `PUBLIC_TITILER_URL` | `https://geo-titiler-<hash>.onrender.com` |
   | `PUBLIC_R2_URL` | `https://pub-<hash>.r2.dev` |
5. Deploy. Vercel auto-deploys on every push to `main`.

---

## Section 2 — Per-project setup (~10 minutes)

Each project gets its own Supabase database. Everything else is shared.

### 2.1 Bootstrap

```bash
./scripts/new_project.sh <project-name>
# Example: ./scripts/new_project.sh nairobi-flood-risk
```

This creates `projects/<name>/` with SQL files, a `.env` stub, and a layer config stub.

### 2.2 Supabase

1. Go to https://supabase.com/dashboard → New project.
   - Name: your project name
   - Password: generate a strong one — you need it for `DATABASE_URL`
   - Region: pick closest to your users (Supabase has EU and US regions on free tier)
2. Wait ~2 minutes for provisioning.
3. SQL Editor → run these files in order:
   ```
   hosting/supabase/setup.sql          ← extensions + schemas + search_path
   projects/<name>/sql/02_tables.sql   ← spatial tables
   projects/<name>/sql/03_indexes.sql  ← spatial + B-tree indexes
   projects/<name>/sql/04_functions.sql ← PL/pgSQL helpers
   ```
4. Copy the connection string:
   Dashboard → Project Settings → Database → Connection string → **URI** (pooler).
   **geo-api** uses the transaction pooler (port 6543):
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
   **geo-martin** uses the session pooler (port 5432) — Martin runs prepared statements at
   startup and hangs on port 6543:
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
   ```
   Paste the appropriate URL into `projects/<name>/.env` → `SUPABASE_DATABASE_URL`.

5. Update Martin on Render: Dashboard → `geo-martin` → Environment → `DATABASE_URL`
   → paste the **port 5432** (session pooler) URL → Save (triggers a redeploy).

### 2.3 Data in R2

Three dedicated buckets keep tile types separate and access controls clean:

```
geo-pmtiles/           ← public, browser range-requests
  <project-name>/
    boundaries.pmtiles
    roads.pmtiles
    imagery.tif        ← COG rasters for TiTiler

geo-parquet/           ← public (read), credentials needed to write
  <project-name>/
    boundaries.parquet
    buildings.parquet  ← DuckDB reads via httpfs (range requests)

geo-uploads/           ← private, managed by the API
  <job-uuid>/
    raw_file.zip       ← deleted automatically after ogr2ogr finishes
```

Sync local files to R2 (load env vars first):
```bash
source .env.cloud

# PMTiles
./scripts/r2_sync.sh data/pmtiles/<name>/ geo-pmtiles/<name>/

# GeoParquet
./scripts/r2_sync.sh data/parquet/<name>/ geo-parquet/<name>/
```

The `geo-uploads` bucket is managed entirely by the API — you never write to it directly.

### 2.4 GitHub Secrets (keep-alive)

1. GitHub → repo → Settings → Secrets and variables → Actions → New secret.
2. Name: `SUPABASE_DATABASE_URL`, value: pooler URL from step 2.2.
3. The workflow in `.github/workflows/keep-supabase-alive.yml` fires Mon + Thu.
   For a second project, add `SUPABASE_DATABASE_URL_PROJECT2` and uncomment the
   second step in the workflow file.

---

## Section 3 — Loading data

There are three ways to load data, suited to different file sizes and workflows:

| Method | Best for | Size limit | Where data lands |
|--------|----------|-----------|-----------------|
| **Web UI** (`/upload`) | Any GDAL format, any size, interactive | No limit | custom `staging.*` table |
| **CLI script** (`load_supabase.sh`) | Local large files, automation | No limit | custom `staging.*` table |
| **API endpoint** (`/ingest/features`) | Programmatic GeoJSON POST | 100k features | `staging.raw_features` |

All three routes land in the `staging` schema. Promote to `geo` when data is validated (§3.3).

---

### 3.1 Web upload UI — `/upload`

Navigate to `https://your-vercel-url/upload` (or `http://localhost:5173/upload` locally).
The "Upload Data" link also appears at the bottom of the map's Layer Control panel.

**How it works — server-side GDAL, no browser memory limit:**

The browser streams the raw file to the API. The API saves it to disk, runs `ogrinfo` to
detect layers, backs it up to R2 `geo-uploads`, then runs `ogr2ogr` server-side to load
directly into Supabase via the direct connection (COPY mode). Progress is tracked in
`staging.ingest_jobs` and streamed back to the browser via SSE.

```
Browser → stream file bytes → Render API → /tmp
                                           ├─ ogrinfo: layer list (returned to browser)
                                           ├─ R2 geo-uploads: durable backup
                                           └─ ogr2ogr → Supabase staging.* (direct port 5432)
                                                        ↑ progress SSE (1s polling of ingest_jobs)
```

**Supported formats — anything ogr2ogr can read:**
| Format | Extension | Notes |
|--------|-----------|-------|
| GeoJSON | `.geojson`, `.json` | Single or multi-layer |
| KML | `.kml` | Placemarks, polygons, lines |
| Shapefile ZIP | `.zip` | ZIP with `.shp`/`.dbf`/`.prj`; multi-SHP ZIPs show a layer picker |
| GeoPackage | `.gpkg` | Multi-layer; layer picker shown |
| GeoParquet | `.parquet` | Spatial Parquet files |
| CSV | `.csv` | Must have `lat`/`lon` columns |
| GML, MapInfo | `.gml`, `.tab` | Any format GDAL supports |

**Workflow:**
1. Drag-drop or browse for your file — any size.
2. The file streams to the server with a live upload progress bar (%).
3. After upload, the server runs `ogrinfo` and shows detected layers.
   - Single-layer files (GeoJSON, KML): layer is auto-selected.
   - Multi-layer files (GeoPackage, Shapefile ZIP): a radio list lets you pick one layer.
4. Set the **target table** (e.g. `staging.kenya_roads`) — auto-suggested from the filename.
   Tick **Overwrite** if you want to replace an existing table.
5. Click **Import** — the server runs `ogr2ogr` and streams progress back.
6. When done, a success panel shows the row count and next-step SQL snippets.
7. **Job history** panel on the right lists all past jobs with status, row count, and errors.
   You can close the tab mid-import — the job continues server-side. Come back and check history.

**What the server does automatically:**
- Reprojects to EPSG:4326
- Promotes to multi-geometry (no Polygon/MultiPolygon type mismatches)
- Appends `sslmode=require` to the Supabase connection string
- Uses PostgreSQL COPY mode (fastest bulk insert) when `SUPABASE_DIRECT_URL` is set
- Backs up the raw file to R2 `geo-uploads` so the job can be retried if the API restarts
- Cleans up `/tmp` after the job completes

**API endpoints behind the UI:**
```
POST /ingest/upload          — upload file, detect layers → {job_id, layers[]}
POST /ingest/process         — start ogr2ogr job          → {job_id, status}
GET  /ingest/job/{id}        — SSE progress stream
GET  /ingest/jobs            — list last 50 jobs
DELETE /ingest/job/{id}      — delete job record + R2 backup
```

---

### 3.2 CLI loader — `scripts/load_supabase.sh`

Use this when running from your local machine for very large datasets (> Render free RAM),
automation scripts, or when you want to load directly without the UI.

**Prerequisites:**
- `ogr2ogr` installed (`brew install gdal` on macOS, `apt install gdal-bin` on Ubuntu)
- `SUPABASE_DIRECT_URL` set in `.env.cloud` — must be the **direct** connection (port 5432),
  not the pooler. Get it from Dashboard → Project Settings → Database → Connection string → URI:
  ```
  postgresql://postgres:PASSWORD@db.XXXX.supabase.co:5432/postgres
  ```

**Usage:**
```bash
# Shapefile ZIP — lists all layers if multiple, loads first one
./scripts/load_supabase.sh data/kenya.zip staging.kenya_admin

# Specific layer from a multi-layer ZIP
./scripts/load_supabase.sh data/kenya.zip staging.kenya_admin --layer adminareas

# GeoJSON
./scripts/load_supabase.sh data/wards.geojson staging.wards

# GeoPackage with specific layer
./scripts/load_supabase.sh data/kenya.gpkg staging.roads --layer roads

# Overwrite existing table
./scripts/load_supabase.sh data/file.geojson staging.layer --overwrite

# Spatial filter — clip to a bounding box before loading
./scripts/load_supabase.sh data/roads.zip staging.nairobi_roads \
  --layer roads_free --bbox 36.65,-1.36,37.10,-1.16
```

The script always reprojects to EPSG:4326, promotes to multi-geometry, and uses COPY mode.

---

### 3.3 Staging → Production (`staging` → `geo` schema)

`staging` is the landing zone. `geo` is what Martin serves as tiles and what the API
exposes. Moving data between them is a SQL step — you decide when data is ready.

**Option A — Copy into an existing `geo` table (recommended for standard layers):**
```sql
-- Promote Kenya admin areas into the geo.boundaries table
INSERT INTO geo.boundaries (name, admin_level, geom)
SELECT
    properties->>'name'         AS name,
    (properties->>'admin_level')::int AS admin_level,
    geom
FROM staging.raw_features
WHERE layer_name = 'kenya_admin'
  AND ST_IsValid(geom);
```

**Option B — Create a new table directly in `geo` from a staging table:**
```sql
-- Promote a CLI-loaded staging table (e.g. staging.kenya_admin) to geo
CREATE TABLE geo.kenya_admin AS
SELECT * FROM staging.kenya_admin;

-- Add a spatial index (Martin needs this)
CREATE INDEX ON geo.kenya_admin USING GIST (geom);

-- Register the geometry column (required for Martin auto-discovery)
-- (PostGIS 3.x does this automatically via geometry_columns view,
--  but run this if Martin doesn't pick up the table)
SELECT Populate_Geometry_Columns('geo.kenya_admin'::regclass);
```

**Option C — Rename a CLI-loaded staging table into `geo`:**
```sql
ALTER TABLE staging.kenya_admin SET SCHEMA geo;
CREATE INDEX IF NOT EXISTS kenya_admin_geom_idx ON geo.kenya_admin USING GIST (geom);
```

**After any of the above — redeploy Martin** so it picks up the new table:

```bash
# Via Render Dashboard:
#   geo-martin → Manual Deploy → Deploy latest commit

# Or trigger via API (replace with your service ID from render.yaml / dashboard URL):
curl -X POST https://api.render.com/v1/services/<SERVICE_ID>/deploys \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" -d '{}'
```

Martin auto-discovers all tables in the `geo` schema that have a registered geometry column.
The tile URL pattern is: `https://geo-martin-<hash>.onrender.com/geo.<table_name>/{z}/{x}/{y}`

**To clean up staging after promotion:**
```sql
-- Remove specific layer from raw_features
DELETE FROM staging.raw_features WHERE layer_name = 'kenya_admin';

-- Or drop a CLI-loaded staging table entirely
DROP TABLE IF EXISTS staging.kenya_admin;
```

---

### 3.4 Martin schema — can I point to a different schema?

Yes. Martin's `from_schemas` config controls which schemas it publishes. Currently set to `geo`
only. To add another schema, edit `martin/config.yaml`:

```yaml
postgres:
  auto_publish:
    from_schemas:
      - geo
      - my_other_schema   # ← add here
```

Then commit and push (Render redeploys automatically). Tables in `staging` and `audit` are
intentionally excluded — `staging` is a landing zone for unvalidated data and `audit` is
internal change history.

---

### 3.5 GeoParquet and PMTiles pipeline

```bash
# Any vector → optimised GeoParquet (Hilbert-sorted, ZSTD compressed, bbox columns)
python scripts/to_geoparquet.py input.shp output.parquet
python scripts/to_geoparquet.py input.geojson output.parquet --bbox "36.5,-1.5,37.2,-0.5"

# GeoParquet → PMTiles (static tiles, served from R2, no tile server needed)
./scripts/to_pmtiles.sh data/input.parquet data/pmtiles/output.pmtiles --max-zoom 16

# Sync PMTiles and GeoParquet to Cloudflare R2
./scripts/r2_sync.sh data/pmtiles/ pmtiles/         # static tiles
./scripts/r2_sync.sh data/parquet/ parquet/          # GeoParquet for DuckDB analytics
```

GeoParquet in R2 is accessed by the FastAPI `/analytics` endpoints via DuckDB's httpfs
extension — no download required, DuckDB uses HTTP range requests to read only the
partitions it needs.

---

### 3.6 Redeploy Martin after schema changes

Martin discovers PostGIS tables only at startup. Any time you add a new table to `geo`:

1. Render Dashboard → `geo-martin` → **Manual Deploy** → **Deploy latest commit**
2. Wait ~30 seconds.
3. Verify: `curl https://geo-martin-<hash>.onrender.com/catalog`

The `/catalog` endpoint lists every published source. If your table isn't there, check:
```sql
SELECT * FROM geometry_columns WHERE f_table_schema = 'geo';
```
If the row is missing, the geometry column wasn't registered — run `Populate_Geometry_Columns`
or recreate the table with an explicit `GEOMETRY(...)` type.

---

## Section 4 — Free tier limits and upgrade triggers

| Service | Free limit | What breaks first | Upgrade cost |
|---------|-----------|------------------|-------------|
| Supabase | 500 MB DB, 2 projects | DB storage (~50M rows) | $25/mo (Pro) |
| Cloudflare R2 | 10 GB storage, 1M writes, 10M reads/mo | Storage if many large PMTiles | $0.015/GB after |
| Render | 512 MB RAM, spins down after 15 min idle | OOM on large DuckDB queries or huge ogr2ogr jobs | $7/mo per service |
| Vercel | Unlimited deploys | Rarely a concern | $20/mo (Pro) |

**R2 bucket breakdown (10 GB total across all buckets):**
- `geo-pmtiles`: PMTiles files are typically 5–200 MB each. 10 GB = ~50–2000 layers.
- `geo-parquet`: GeoParquet with ZSTD compression is very compact. Country-level OSM ≈ 100–500 MB.
- `geo-uploads`: Temp only — files are deleted after ogr2ogr finishes. Rarely holds > 1 GB at a time.

**Render RAM and ogr2ogr:**
Render's free tier has 512 MB RAM. `ogr2ogr` with COPY mode is streaming — it doesn't load the
whole file into memory. In practice, files up to ~500 MB process fine. For the 1.2 GB Kenya
buildings shapefile, run the CLI script locally instead (your machine has more RAM and ogr2ogr
writes directly to Supabase over the network).

**Rule of thumb**: 2 full country-level projects (PostGIS + GeoParquet + PMTiles) fit comfortably
within all free tiers.

---

## Section 5 — Troubleshooting

**Supabase project paused**
Free projects pause after 7 days without a query. Check GitHub Actions → keep-supabase-alive
ran recently. To unpause manually: Supabase Dashboard → project → Restore project.
The keep-alive workflow runs Mon/Thu — if a project was idle over a long weekend, it may pause.

**Martin 500 error / "function st_asmvt does not exist"**
Martin can't find PostGIS functions. Root cause: `search_path` doesn't include `extensions`.
Fix: re-run the `ALTER ROLE` statements in `hosting/supabase/setup.sql`, then start a new
connection (the SQL Editor session caches the old search_path).
Also check `DATABASE_URL` uses the **pooler URL port 6543**, not the direct connection port 5432.
Render's free tier reuses connections aggressively — the pooler handles this; port 5432 won't.

**Martin shows no layers / empty catalog at `/catalog`**
Martin only publishes tables in the `geo` schema that have a geometry column registered in
`geometry_columns`. Verify your table exists:
```sql
SELECT * FROM geometry_columns WHERE f_table_schema = 'geo';
```
If empty, the table's geometry column wasn't created with `AddGeometryColumn()` or
`CREATE TABLE ... geom GEOMETRY(...)`. Both work — check PostGIS version compatibility.

**PMTiles not loading in browser (CORS error)**
R2 bucket's CORS config must allow the `Range` header. Re-apply to `geo-pmtiles`:
```bash
wrangler r2 bucket cors put geo-pmtiles --file hosting/r2_cors.json
```
Also verify public access is enabled (R2 → `geo-pmtiles` → Settings → Public access).

**DuckDB can't read GeoParquet from R2 ("403 Forbidden")**
Check `R2_ENDPOINT` format — must be `https://<account_id>.r2.cloudflarestorage.com`
with no trailing slash. Verify the R2 API token covers the `geo-parquet` bucket and has
Read & Write permissions. Scope matters — a token scoped to one bucket won't access another.

**Web upload stuck on "Queued — starting…" and never progresses**
The API background task is running but `staging.ingest_jobs` isn't being updated.
Check Render logs for `geo-api` — common causes:
- `SUPABASE_DIRECT_URL` not set: ogr2ogr falls back to the pooler URL which may reject COPY mode.
  Add `SUPABASE_DIRECT_URL` (port 5432 direct) to the `geo-api` Render service.
- `ogrinfo`/`ogr2ogr` not found: the Docker image didn't include `gdal-bin`. Trigger a fresh
  deploy (Render → `geo-api` → Manual Deploy) so the updated Dockerfile is used.
- File gone from `/tmp`: Render restarts clear `/tmp`. If you see "File no longer available",
  the job will attempt to restore from R2 `geo-uploads`. If R2 credentials aren't set, re-upload.

**Web upload: "No readable layers found in this file"**
`ogrinfo` couldn't open the file. Possible causes:
- Corrupt or incomplete upload (retry).
- Format not supported by the GDAL version in the Docker image (check Render logs for the
  ogrinfo error message).
- ZIP file has no `.shp` inside — the upload page expects Shapefile ZIPs, not arbitrary ZIPs.

**Web upload: ogr2ogr fails with geometry type error**
ogr2ogr promotes all geometries to multi-type (`-nlt PROMOTE_TO_MULTI`), which handles
most Polygon/MultiPolygon mix issues. If you still see a type error, check the `error` field
in the Job history panel — the full ogr2ogr error message is stored there.

**Job shows "done" but table doesn't appear in Supabase**
The `target_table` might have been created in the wrong schema. Run in SQL Editor:
```sql
SELECT schemaname, tablename FROM pg_tables WHERE tablename ILIKE '%your_table%';
```
Also check: if `overwrite` was NOT set and the table already existed with different column
types, ogr2ogr appended to it and the row count includes both old and new rows.

**Render cold start: first request takes 3-5 seconds**
Free tier services spin down after 15 minutes of inactivity. The first request wakes them.
This is expected for demos and low-traffic projects. To eliminate cold starts: upgrade
`geo-api` to Render Starter ($7/mo) — Martin and TiTiler are rarely the bottleneck.

**TiTiler "No such file or directory" for COG on R2**
Verify `AWS_S3_ENDPOINT` on the `geo-titiler` Render service matches your R2 endpoint exactly.
GDAL's VSI S3 driver uses this for all `s3://` paths. The COG URL passed to TiTiler must use
`s3://<bucket>/<path>` format when reading from R2 via the API.

**FastAPI health check failing on Render**
Render's health check hits `/health`. If it returns a non-200, the service is marked unhealthy
and Render restarts it. Check Render logs for the actual error — common causes are
`DATABASE_URL` pointing to the wrong Supabase project, or asyncpg failing to connect because
the Supabase project is paused.

**`ogr2ogr` fails with "SSL connection required"**
Supabase requires SSL. Add `?sslmode=require` to the connection string if ogr2ogr rejects it:
```bash
ogr2ogr -f PostgreSQL "PG:$SUPABASE_DATABASE_URL?sslmode=require" input.geojson ...
```
