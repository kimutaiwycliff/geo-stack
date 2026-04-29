# CLAUDE.md — geo-stack project context

## What this project is
A reusable open-source geospatial infrastructure stack for Wycliff Kimutai (Senior GIS Developer).
Three deployment modes from one codebase: local M1 dev, cloud-free (Render+R2+Vercel), production VPS.

## Stack
| Component | Technology |
|-----------|-----------|
| Spatial DB (writes) | PostGIS 17 / PostgreSQL 17 |
| Analytics (reads) | DuckDB + GeoParquet |
| Live vector tiles | Martin (Rust, MVT from PostGIS) |
| Static vector tiles | PMTiles (Cloudflare R2) |
| Raster tiles | TiTiler (COG via GDAL) |
| API | FastAPI + Python 3.12 |
| Frontend | SvelteKit 5 + MapLibre GL JS |
| Reverse proxy | Caddy (auto HTTPS in production) |

## Key architectural decisions
- PostGIS owns **writes** and KNN queries. DuckDB owns **analytics** on GeoParquet.
- All geometry is stored/served in **EPSG:4326** externally. Reproject inside DB as needed.
- Martin publishes from the `geo` schema only — `staging` and `audit` are never exposed.
- DuckDB is embedded in the FastAPI process (no separate server). One connection per worker.
- PMTiles served via HTTP range requests — no tile server, just R2 or any static host.

## Running locally (Apple M1)
```bash
cp .env.example .env.local
# Edit .env.local: set POSTGRES_PASSWORD=anything_for_local
docker compose -f docker-compose.yml -f docker-compose.local.yml up
# Open http://localhost:5173
```

## Running in production (VPS)
```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

## Where to look for things
| Thing | Location |
|-------|---------|
| API routes | `api/routers/` |
| DuckDB query helpers | `api/spatial/queries/` |
| PostGIS init SQL | `db/init/` |
| Martin tile config | `martin/config.yaml` |
| Layer registry (per-project edit point) | `frontend/src/lib/config/layers.ts` |
| Deploy runbook | `DEPLOYMENT.md` |
| Data pipeline scripts | `scripts/` |

## Per-project workflow
1. **Load data**: `scripts/load_postgis.sh` (live) or `scripts/to_geoparquet.py` (analytics)
2. **Choose tile type**: see `layers.ts` comments (mvt vs pmtiles vs geojson vs raster)
3. **Add layer**: edit `frontend/src/lib/config/layers.ts`
4. **Static tiles**: `scripts/to_pmtiles.sh` → `scripts/r2_sync.sh`

## PostGIS schemas
- `geo` — validated production data (Martin publishes from here)
- `staging` — raw imports before validation
- `audit` — change log for geo table modifications

## Python conventions
- Python 3.12+, `ruff` for linting
- `pydantic-settings` for all config (never `os.getenv()` directly in routes)
- `asyncpg` for PostGIS (async), `duckdb` in thread executor (not thread-safe for writes)
- All route functions have type hints; pydantic v2 models for request/response schemas

## Frontend conventions
- Svelte 5 runes syntax
- Layer config in `layers.ts` drives the entire UI — no hardcoded layer IDs anywhere else
- Runtime API URLs fetched from `/api/config` to support Docker env var injection
- PMTiles protocol registered globally in `MapLibre.svelte` before any source is added
