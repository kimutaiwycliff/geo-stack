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

## Section 3 — Loading data and redeploying Martin

### Redeploy Martin after adding a new Supabase table

Martin (running on Render) discovers PostGIS tables **only when it starts**. After you
load a new table into Supabase, Martin won't serve it until you trigger a redeploy:

1. Render Dashboard → `geo-martin` → top-right **Manual Deploy** → **Deploy latest commit**
2. Wait ~30 seconds for the new instance to start.
3. Verify: `curl https://geo-martin-<hash>.onrender.com/geo.my_table`

Alternatively, update any environment variable on the `geo-martin` service and save —
Render redeploys automatically on any env change.

### Data loading reference

```bash
# Any vector format → optimised GeoParquet (Hilbert-sorted, bbox columns)
python scripts/to_geoparquet.py input.shp output.parquet
python scripts/to_geoparquet.py input.geojson output.parquet --bbox "36.5,-1.5,37.2,-0.5"

# Vector → PostGIS on Supabase (for live MVT layers via Martin)
source projects/<name>/.env
ogr2ogr -f PostgreSQL PG:"$SUPABASE_DATABASE_URL" input.geojson \
  -nln geo.my_layer -lco GEOMETRY_NAME=geom -lco FID=id \
  -t_srs EPSG:4326

# GeoParquet → PMTiles (static layers, served from R2, no tile server)
./scripts/to_pmtiles.sh data/input.parquet data/pmtiles/output.pmtiles --max-zoom 16

# Sync to R2
source projects/<name>/.env
./scripts/r2_sync.sh data/pmtiles/ pmtiles/           # static tiles
./scripts/r2_sync.sh projects/<name>/data/ <name>/    # GeoParquet for DuckDB

# Overture Maps extract (buildings, roads, POIs for any bbox)
python scripts/overture_extract.py \
  --bbox "33.9,-4.7,41.9,5.0" \
  --theme buildings \
  --output data/kenya_buildings.parquet

# Load Overture data into Supabase
source projects/<name>/.env
./scripts/load_postgis.sh data/kenya_buildings.parquet geo.buildings
```

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
