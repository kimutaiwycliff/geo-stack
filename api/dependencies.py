"""FastAPI dependency injection: DuckDB connection and PostGIS pool accessors."""

from collections.abc import AsyncGenerator
from typing import Annotated

import asyncpg
import duckdb
from fastapi import Depends

from spatial.duckdb_engine import get_duckdb_conn
from spatial.postgis_engine import get_postgis_pool


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Yield a single asyncpg connection from the PostGIS pool."""
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        yield conn


async def get_duck() -> AsyncGenerator[duckdb.DuckDBPyConnection, None]:
    """Yield a DuckDB thread-local connection."""
    async with get_duckdb_conn() as conn:
        yield conn


# Typed dependency aliases for use in route function signatures
PostGIS = Annotated[asyncpg.Connection, Depends(get_db)]
DuckDB = Annotated[duckdb.DuckDBPyConnection, Depends(get_duck)]
