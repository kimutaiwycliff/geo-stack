"""GET /health — liveness and readiness check."""

from fastapi import APIRouter
from pydantic import BaseModel

from spatial.duckdb_engine import verify as duckdb_verify
from spatial.postgis_engine import verify as postgis_verify

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    postgis: bool
    duckdb: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Returns 200 when both PostGIS and DuckDB are reachable."""
    pg_ok = await postgis_verify()
    duck_ok = await duckdb_verify()
    return HealthResponse(
        status="ok" if pg_ok and duck_ok else "degraded",
        postgis=pg_ok,
        duckdb=duck_ok,
    )
