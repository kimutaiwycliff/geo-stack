# scripts/

Data pipeline tools for geo-stack.

| Script | Purpose | Requires |
|--------|---------|----------|
| `to_geoparquet.py` | Convert any vector format (SHP, GPKG, GeoJSON) → optimized GeoParquet | Python venv + deps |
| `to_pmtiles.sh` | GeoJSON/GeoParquet → PMTiles via tippecanoe | `tippecanoe`, `pmtiles`, `duckdb` CLI |
| `load_postgis.sh` | Load GeoParquet/GeoJSON into PostGIS via ogr2ogr | `gdal`, running PostGIS |
| `overture_extract.py` | Extract Overture Maps data for a bbox | Python venv + `duckdb` |
| `optimize_parquet.py` | Hilbert sort + bbox columns on existing GeoParquet | Python venv + deps |
| `r2_sync.sh` | Upload data/ to Cloudflare R2 | `awscli` |
| `new_project.sh` | Bootstrap a new project workspace | nothing |

---

## Setup — install dependencies

### Python virtual environment (all platforms)

Modern Linux distros (Ubuntu 22.04+, Debian 12+) block system-wide `pip install`
with "externally managed environment". Use a venv everywhere — it also keeps
geo deps isolated from other projects.

```bash
# Create venv once (from the repo root)
python3 -m venv .venv

# Activate — do this every terminal session before running scripts
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows (PowerShell)

# Install Python deps (inside activated venv)
pip install duckdb geopandas pyarrow shapely
```

To deactivate when done: `deactivate`

You can tell the venv is active because your prompt shows `(.venv)`.

---

### CLI tools — macOS

```bash
brew install tippecanoe
brew install protomaps/homebrew-protomaps/go-pmtiles
brew install duckdb
brew install awscli
```

### CLI tools — Ubuntu / Debian (Linux)

```bash
# GDAL / ogr2ogr
sudo apt update && sudo apt install -y gdal-bin

# tippecanoe — build from source (no apt package)
sudo apt install -y build-essential libsqlite3-dev zlib1g-dev
git clone https://github.com/felt/tippecanoe.git
cd tippecanoe && make -j$(nproc) && sudo make install && cd ..

# pmtiles CLI — download binary from GitHub releases
PMTILES_VERSION=$(curl -s https://api.github.com/repos/protomaps/go-pmtiles/releases/latest | grep tag_name | cut -d'"' -f4)
curl -Lo pmtiles.tar.gz "https://github.com/protomaps/go-pmtiles/releases/download/${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz"
tar -xzf pmtiles.tar.gz pmtiles && sudo mv pmtiles /usr/local/bin/ && rm pmtiles.tar.gz

# duckdb CLI
curl -Lo duckdb.gz https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.gz
gunzip duckdb.gz && chmod +x duckdb && sudo mv duckdb /usr/local/bin/

# awscli
sudo apt install -y awscli
# or: pip install awscli  (inside venv)
```

### CLI tools — Windows (WSL2 recommended)

Run everything inside WSL2 (Ubuntu). Once inside WSL, follow the Ubuntu steps above.

```powershell
# Install WSL2 with Ubuntu (PowerShell, run as Administrator)
wsl --install
```

Then open the Ubuntu terminal and proceed with the Linux instructions.

---

### Credentials — `.env.local`

Fill in your Cloudflare R2 values (get them from Cloudflare dashboard → R2 → Manage R2 API Tokens):

```bash
R2_ENDPOINT=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
R2_ACCESS_KEY=your_access_key_id
R2_SECRET_KEY=your_secret_access_key
R2_BUCKET_NAME=geo-data
R2_PUBLIC_URL=https://pub-xxxx.r2.dev   # your public bucket URL
```

Load before running sync commands:

```bash
source .env.local       # macOS / Linux / WSL
```

## Quick workflow: from raw data to map

```bash
# 1. Convert raw shapefile to GeoParquet
python scripts/to_geoparquet.py raw/nairobi_buildings.shp data/buildings.parquet

# 2. Optimize (if file was not created by step 1)
python scripts/optimize_parquet.py data/buildings.parquet data/buildings.parquet

# 3a. For live data: load into PostGIS
./scripts/load_postgis.sh data/buildings.parquet geo.buildings

# 3b. For static tiles: generate PMTiles
./scripts/to_pmtiles.sh data/buildings.parquet data/pmtiles/buildings.pmtiles

# 4. Upload to R2
./scripts/r2_sync.sh data/pmtiles/
./scripts/r2_sync.sh data/buildings.parquet

# 5. Add to frontend/src/lib/config/layers.ts
```

---

## Finding the bounds for a layer

Every layer in `layers.ts` can have a `bounds: [west, south, east, north]` field
that powers the zoom-to button in the layer control. You rarely need to calculate
this yourself — the tools you're already using expose it directly.

### MVT layers (Martin)

Martin exposes a TileJSON endpoint for every published source. It includes bounds
computed from the PostGIS table extent:

```bash
# Local dev
curl http://localhost:3000/geo.kenya_roads | python3 -m json.tool | grep bounds
# "bounds": [33.909821, -4.720017, 41.899578, 4.622525]

# Copy those four numbers directly into layers.ts:
# bounds: [33.91, -4.72, 41.90, 4.62]
```

### PostGIS tables

Run this in psql, DBeaver, or the Supabase SQL Editor:

```sql
SELECT
  ST_XMin(ST_Extent(geom)) AS west,
  ST_YMin(ST_Extent(geom)) AS south,
  ST_XMax(ST_Extent(geom)) AS east,
  ST_YMax(ST_Extent(geom)) AS north
FROM geo.kenya_roads;
```

`ST_Extent` is exact. For very large tables use `ST_EstimatedExtent` instead — it
reads the statistics table and is nearly instantaneous:

```sql
SELECT ST_EstimatedExtent('geo', 'kenya_roads', 'geom');
-- Returns: BOX(33.9 -4.7, 41.9 5.0)
-- → bounds: [33.9, -4.7, 41.9, 5.0]
```

### PMTiles files

The PMTiles file header stores bounds. Read it before uploading to R2:

```bash
pmtiles show data/pmtiles/nairobi_wards.pmtiles
# bounds: 36.650000,-1.440000,37.100000,-1.160000
# → bounds: [36.65, -1.44, 37.10, -1.16]
```

### GeoParquet or GeoJSON (DuckDB one-liner)

```bash
duckdb -c "
  LOAD spatial;
  SELECT
    ST_XMin(ST_Extent(geom)) AS west,
    ST_YMin(ST_Extent(geom)) AS south,
    ST_XMax(ST_Extent(geom)) AS east,
    ST_YMax(ST_Extent(geom)) AS north
  FROM read_parquet('data/my_layer.parquet');
"

# Works on GeoJSON too — replace read_parquet with ST_Read:
duckdb -c "
  LOAD spatial;
  SELECT ST_XMin(ST_Extent(geom)) w, ST_YMin(ST_Extent(geom)) s,
         ST_XMax(ST_Extent(geom)) e, ST_YMax(ST_Extent(geom)) n
  FROM ST_Read('data/my_layer.geojson');
"
```

### Any file format (ogrinfo — fastest for a quick check)

```bash
ogrinfo -al -so data/my_layer.geojson
# Extent: (36.650000, -1.440000) - (37.100000, -1.160000)
#           west      south           east      north
# → bounds: [36.65, -1.44, 37.10, -1.16]

# Also works on shapefiles and GeoPackages:
ogrinfo -al -so data/kenya_roads.shp
ogrinfo -al -so gadm41_KEN.gpkg   # lists all layers + each layer's extent
```

### Python (when already in a GeoPandas workflow)

```python
import geopandas as gpd

gdf = gpd.read_file('data/my_layer.geojson')
w, s, e, n = gdf.to_crs('EPSG:4326').total_bounds
print(f"bounds: [{w:.4f}, {s:.4f}, {e:.4f}, {n:.4f}]")
```

### Quick rule of thumb

| Layer type | Where to get bounds |
|-----------|-------------------|
| MVT (Martin) | `curl localhost:3000/<source-name>` → `bounds` field |
| PMTiles | `pmtiles show <file>` |
| PostGIS table | `SELECT ST_EstimatedExtent(...)` |
| Parquet / GeoJSON | DuckDB one-liner or `ogrinfo -al -so` |
| Shapefile / GPKG | `ogrinfo -al -so <file>` |
