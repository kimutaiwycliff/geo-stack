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
  │     ├─→ Render       FastAPI /features, /analytics, /stac
  │     │     └─→ Supabase  PostGIS (asyncpg pool, pooler port 6543)
  │     │     └─→ R2        DuckDB reads GeoParquet via httpfs
  │     │
  │     ├─→ Render       Martin MVT tiles (/geo/boundaries/{z}/{x}/{y})
  │     │     └─→ Supabase  PostGIS (direct read, geo schema only)
  │     │
  │     ├─→ Render       TiTiler raster tiles
  │     │     └─→ R2        COG files via GDAL VSI S3
  │     │
  │     └─→ R2           PMTiles (browser fetches directly, no server)
```

---

## Section 1 — One-time setup

Do this once. All projects share the same Render services, R2 bucket, and Vercel team.

### 1.1 Cloudflare R2

1. Create a Cloudflare account (free, no credit card).
2. R2 → Create bucket → name: `geo-data` → Location: auto.
3. Enable public access: R2 → `geo-data` → Settings → Public access → Allow public.
   This gives you a URL like `https://pub-<hash>.r2.dev`.
4. Apply CORS config so browsers can load PMTiles and COGs:
   ```bash
   npm install -g wrangler
   wrangler login
   wrangler r2 bucket cors put geo-data --file hosting/r2_cors.json
   ```
   The `Range` header in the CORS config is critical — PMTiles and COG both rely on
   HTTP range requests to fetch only the tile/chunk they need.
5. Create an API token: R2 → Manage R2 API Tokens → Create API Token.
   - Permissions: Object Read & Write
   - Scope: `geo-data` bucket only
   - Copy `Access Key ID` and `Secret Access Key` — you need these for `.env.cloud`.

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
   | `DATABASE_URL` | Supabase pooler URL (port 6543) |
   | `R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
   | `R2_ACCESS_KEY` | Your R2 access key |
   | `R2_SECRET_KEY` | Your R2 secret key |
   | `R2_BUCKET_NAME` | `geo-data` |
   | `R2_PUBLIC_URL` | `https://pub-<hash>.r2.dev` |
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

GeoParquet and PMTiles go in a project subfolder of the `geo-data` bucket:
```
geo-data/
  <project-name>/
    boundaries.pmtiles
    my_layer.parquet
  another-project/
    ...
```

Load env vars first, then sync:
```bash
source projects/<name>/.env
./scripts/r2_sync.sh data/pmtiles/<name>/ pmtiles/<name>/
./scripts/r2_sync.sh projects/<name>/data/ <name>/
```

### 2.4 GitHub Secrets (keep-alive)

1. GitHub → repo → Settings → Secrets and variables → Actions → New secret.
2. Name: `SUPABASE_DATABASE_URL`, value: pooler URL from step 2.2.
3. The workflow in `.github/workflows/keep-supabase-alive.yml` fires Mon + Thu.
   For a second project, add `SUPABASE_DATABASE_URL_PROJECT2` and uncomment the
   second step in the workflow file.

---

## Section 3 — Loading data

There are two ways to get data into the stack: **the browser upload app** (GeoJSON, KML,
Shapefile ZIP, CSV up to 100,000 features) and **the CLI loader** (any GDAL-supported format,
any size, direct to Supabase). Both land data in `staging.raw_features` or a custom staging
table. Production data lives in the `geo` schema, which Martin serves as MVT tiles.

---

### 3.1 Browser upload (UI mini-app)

Navigate to `https://your-vercel-url/upload` (or `http://localhost:5173/upload` locally).

**Supported formats:**
| Format | Max size | Notes |
|--------|----------|-------|
| GeoJSON (`.geojson`, `.json`) | 100k features | FeatureCollection, Feature, or bare geometry |
| KML (`.kml`) | 100k features | Parsed with `@mapbox/togeojson` |
| Shapefile ZIP (`.zip`) | 100k features | ZIP must contain `.shp`, `.dbf`, `.prj` |
| CSV (`.csv`) | 100k features | Must have `lat`/`lon` or `latitude`/`longitude` columns |

**Workflow:**
1. Drag-drop or browse for your file.
2. Review the validation panel — feature count, geometry types, extent, any CRS warnings.
3. Enter a layer name (auto-suggested from the filename).
4. Click **Upload** — a progress bar streams from the API as batches of 500 features are inserted.
5. On completion, the layer appears in the **Staging layers** panel below.

All uploads land in `staging.raw_features` with columns:
`id · source · layer_name · properties (JSONB) · geom (geometry, EPSG:4326) · imported_at`

To use the data, promote it to the `geo` schema (see §3.3).

---

### 3.2 CLI loader — `scripts/load_supabase.sh`

For large files, GeoPackage, GeoParquet, or any format GDAL can read. Loads directly
into Supabase via `ogr2ogr` COPY mode — much faster than row-by-row inserts.

**Prerequisites:**
- `ogr2ogr` installed (`brew install gdal` on macOS, `apt install gdal-bin` on Ubuntu)
- `SUPABASE_DIRECT_URL` set in `.env.cloud` — must be the **direct** connection (port 5432),
  NOT the pooler. Dashboard → Project Settings → Database → Connection string → URI (direct):
  ```
  postgresql://postgres:PASSWORD@db.XXXX.supabase.co:5432/postgres
  ```

**Basic usage:**
```bash
# Shapefile ZIP (auto-extracts; if multiple layers, lists them and loads first)
./scripts/load_supabase.sh data/kenya.zip staging.kenya_admin

# Specific layer from a multi-layer ZIP
./scripts/load_supabase.sh data/kenya.zip staging.kenya_admin --layer adminareas

# GeoJSON into staging
./scripts/load_supabase.sh data/wards.geojson staging.wards

# GeoPackage (specific layer)
./scripts/load_supabase.sh data/kenya.gpkg staging.roads --layer roads

# Overwrite an existing table
./scripts/load_supabase.sh data/file.geojson staging.layer --overwrite

# Spatial filter — clip to Nairobi bbox before loading
./scripts/load_supabase.sh data/roads.shp staging.nairobi_roads --bbox 36.65,-1.36,37.10,-1.16
```

The script always:
- Reprojects to EPSG:4326
- Promotes to multi-geometry (avoids Polygon/MultiPolygon mismatches)
- Appends SSL (`?sslmode=require`) if not already in the URL
- Prints a row count and next-step hints on completion

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
| Supabase | 500 MB DB, 2 projects | DB storage at ~50M parcel rows | $25/mo (Pro) |
| Cloudflare R2 | 10 GB storage, 10M GET/mo | Storage at ~10K PMTiles | $0.015/GB after |
| Render | 512 MB RAM, spins down | OOM on large DuckDB queries | $7/mo per service |
| Vercel | Unlimited deploys | Rarely a concern | $20/mo (Pro) |

**Rule of thumb**: you can run 2 full projects (PostGIS + GeoParquet + PMTiles) within
the free limits for most city-scale or country-level GIS datasets.

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
R2 bucket's CORS config must allow the `Range` header. Re-apply:
```bash
wrangler r2 bucket cors put geo-data --file hosting/r2_cors.json
```
Also verify public access is enabled on the bucket (R2 → `geo-data` → Settings → Public access).

**DuckDB can't read GeoParquet from R2 ("403 Forbidden")**
Check `R2_ENDPOINT` format — it must be `https://<account_id>.r2.cloudflarestorage.com`
with no trailing slash. Also verify the R2 API token has read access on the `geo-data` bucket,
not account-wide (scope matters on R2 tokens).

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
