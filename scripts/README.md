# scripts/

Data pipeline tools for geo-stack.

| Script | Purpose | Requires |
|--------|---------|----------|
| `to_geoparquet.py` | Convert any vector format (SHP, GPKG, GeoJSON) → optimized GeoParquet | `pip install duckdb geopandas pyarrow` |
| `to_pmtiles.sh` | GeoJSON/GeoParquet → PMTiles via tippecanoe | `tippecanoe`, `pmtiles`, `duckdb` CLI |
| `load_postgis.sh` | Load GeoParquet/GeoJSON into PostGIS via ogr2ogr | `gdal`, running PostGIS |
| `overture_extract.py` | Extract Overture Maps data for a bbox | `pip install duckdb` |
| `optimize_parquet.py` | Hilbert sort + bbox columns on existing GeoParquet | `pip install duckdb geopandas pyarrow` |
| `r2_sync.sh` | Upload data/ to Cloudflare R2 | `awscli` |
| `new_project.sh` | Bootstrap a new project workspace | nothing |

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
