# data/

Mount point for GeoParquet files and generated PMTiles.

## Structure

```
data/
├── sample/         # Small sample datasets (committed to git for demos)
│   ├── nairobi_wards.parquet      # Nairobi ward boundaries — run overture_extract.py to populate
│   └── kenya_admin.parquet        # Kenya ADM2 — run overture_extract.py to populate
└── pmtiles/        # Generated .pmtiles files (git-ignored — generate locally or download from R2)
```

## Populate sample data from Overture Maps

```bash
# Nairobi ward-level boundaries
python scripts/overture_extract.py \
  --bbox "36.65,-1.44,37.10,-1.16" \
  --theme divisions \
  --output data/sample/nairobi_wards.parquet

# Kenya ADM2 (all counties)
python scripts/overture_extract.py \
  --bbox "33.9,-4.7,41.9,5.0" \
  --theme divisions \
  --output data/sample/kenya_admin.parquet

# Nairobi POIs
python scripts/overture_extract.py \
  --bbox "36.65,-1.44,37.10,-1.16" \
  --theme places \
  --output data/sample/nairobi_poi.parquet
```

## Add your project data

1. Drop GeoParquet files here (or in a subdirectory)
2. They'll be auto-discovered by the FastAPI `/stac` catalog
3. Query via `/analytics/parquet?file=yourfile.parquet&bbox=...`
4. Large files → store on R2 and reference by `s3://` URL
