"""
geo-stack FastAPI application.

Startup sequence:
  1. Verify DuckDB spatial extension loads
  2. Establish asyncpg PostGIS connection pool
  3. Log all GeoParquet files found in DATA_DIR
  4. Register routers and middleware
"""

import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import settings
from routers import analytics, features, health, ingest, stac, tiles
from spatial.duckdb_engine import init_duckdb, shutdown_duckdb
from spatial.postgis_engine import close_postgis_pool, init_postgis_pool

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("geo-stack.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("Starting geo-stack API (env=%s)", settings.env)

    # DuckDB: embedded, loaded once per worker process
    await init_duckdb()
    log.info("DuckDB spatial engine ready")

    # PostGIS: async connection pool
    await init_postgis_pool()
    log.info("PostGIS pool ready (size=%d)", settings.db_pool_size)

    # Log available GeoParquet files so ops can see what data is mounted
    data_path = Path(settings.data_dir)
    if data_path.exists():
        parquet_files = list(data_path.rglob("*.parquet"))
        if parquet_files:
            log.info("Found %d GeoParquet file(s) in %s:", len(parquet_files), settings.data_dir)
            for f in parquet_files:
                size_mb = f.stat().st_size / 1_048_576
                log.info("  %s (%.1f MB)", f.relative_to(data_path), size_mb)
        else:
            log.info("No GeoParquet files in %s (mount ./data to add some)", settings.data_dir)

    yield

    # Cleanup
    await close_postgis_pool()
    await shutdown_duckdb()
    log.info("Shutdown complete")


limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.api_rate_limit}/minute"])

app = FastAPI(
    title="geo-stack API",
    description="Spatial API: GeoJSON from PostGIS, analytics from DuckDB, STAC catalog for GeoParquet",
    version="0.1.0",
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    log.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Mount routers
app.include_router(health.router, tags=["health"])
app.include_router(features.router, prefix="/features", tags=["features"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(tiles.router, prefix="/tiles", tags=["tiles"])
app.include_router(stac.router, prefix="/stac", tags=["stac"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
