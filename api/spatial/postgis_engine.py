"""
asyncpg connection pool for PostGIS.

Pool size is configured via DB_POOL_SIZE env var.
A custom geometry codec converts PostGIS WKB hex strings to raw bytes
so geometry values pass through transparently to the API layer.
"""

import json
import logging

import asyncpg

from config import settings

log = logging.getLogger("geo-stack.postgis")

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Called by asyncpg for each new connection in the pool."""
    # Discover which schema owns the PostGIS geometry type at runtime.
    # Local Docker installs PostGIS into 'public'; Supabase installs it into 'extensions'.
    # Hardcoding 'public' causes ValueError on Supabase.
    schema = await conn.fetchval(
        "SELECT n.nspname FROM pg_type t "
        "JOIN pg_namespace n ON t.typnamespace = n.oid "
        "WHERE t.typname = 'geometry' LIMIT 1"
    )
    if schema is None:
        log.warning("PostGIS 'geometry' type not found — is the PostGIS extension installed?")
        return
    await conn.set_type_codec(
        "geometry",
        encoder=lambda v: v,
        decoder=lambda v: v,
        schema=schema,
        format="text",
    )
    for pg_type in ("json", "jsonb"):
        await conn.set_type_codec(
            pg_type,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


async def init_postgis_pool() -> None:
    """Create the asyncpg pool at application startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=settings.db_pool_size,
        command_timeout=30,
        init=_init_connection,
        # Required when connecting through PgBouncer (e.g. Supabase) in
        # transaction or statement pool mode — disables asyncpg's prepared
        # statement cache so it never sends named PREPARE commands.
        statement_cache_size=0,
    )
    # Verify connectivity
    async with _pool.acquire() as conn:
        version = await conn.fetchval("SELECT PostGIS_Version()")
        log.info("PostGIS %s connected (pool max=%d)", version, settings.db_pool_size)


async def close_postgis_pool() -> None:
    """Close the pool gracefully at application shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_postgis_pool() -> asyncpg.Pool:
    """Return the module-level pool; raises if not initialised."""
    if _pool is None:
        raise RuntimeError("PostGIS pool not initialised — call init_postgis_pool() at startup")
    return _pool


async def verify() -> bool:
    """Quick liveness check used by /health endpoint."""
    try:
        pool = await get_postgis_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1
    except Exception as exc:
        log.error("PostGIS verification failed: %s", exc)
        return False
