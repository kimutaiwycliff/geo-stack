"""
DuckDB engine for geo-stack.

DuckDB is embedded — no separate server process.
One persistent connection per worker process, managed here.
Used exclusively for analytics queries against GeoParquet files
and optionally S3/R2 objects via the httpfs extension.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from threading import Lock

import duckdb

from config import settings

log = logging.getLogger("geo-stack.duckdb")

# Module-level state: one connection per Python process
_conn: duckdb.DuckDBPyConnection | None = None
_lock = Lock()

SLOW_QUERY_THRESHOLD_S = 1.0


def _build_init_sql() -> list[str]:
    """Return SQL statements to run on every new DuckDB connection."""
    statements = [
        # Extensions are pre-installed in the Docker image (Dockerfile RUN step).
        # INSTALL is kept as a no-op fallback for local dev outside Docker.
        "INSTALL spatial;",
        "LOAD spatial;",
        "INSTALL httpfs;",
        "LOAD httpfs;",
        f"SET threads = {settings.duckdb_threads};",
        f"SET memory_limit = '{settings.duckdb_memory}';",
    ]

    if settings.r2_endpoint and settings.r2_access_key:
        statements += [
            f"SET s3_endpoint = '{settings.r2_endpoint.replace('https://', '')}';",
            f"SET s3_access_key_id = '{settings.r2_access_key}';",
            f"SET s3_secret_access_key = '{settings.r2_secret_key}';",
            "SET s3_region = 'auto';",
            "SET s3_url_style = 'path';",
        ]
        log.info("DuckDB httpfs configured for Cloudflare R2")

    return statements


def _make_connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(database=":memory:")
    for sql in _build_init_sql():
        conn.execute(sql)
    return conn


async def init_duckdb() -> None:
    """Called at FastAPI startup to pre-warm the DuckDB connection."""
    global _conn
    loop = asyncio.get_running_loop()
    _conn = await loop.run_in_executor(None, _make_connection)
    log.info("DuckDB connection initialised (threads=%d, memory=%s)",
             settings.duckdb_threads, settings.duckdb_memory)


async def shutdown_duckdb() -> None:
    """Called at FastAPI shutdown."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None


@asynccontextmanager
async def get_duckdb_conn() -> AsyncGenerator[duckdb.DuckDBPyConnection, None]:
    """
    Yield the module-level DuckDB connection.
    DuckDB is not thread-safe for concurrent writes, but geo-stack only reads.
    Heavy queries run in a thread pool executor to avoid blocking the event loop.
    """
    global _conn
    if _conn is None:
        loop = asyncio.get_running_loop()
        _conn = await loop.run_in_executor(None, _make_connection)

    yield _conn


async def execute_query(sql: str, params: list | None = None) -> list[dict]:
    """
    Run a DuckDB query in a thread pool executor (non-blocking).
    Logs a warning for queries exceeding SLOW_QUERY_THRESHOLD_S.
    Returns a list of row dicts.
    """
    loop = asyncio.get_running_loop()

    def _run() -> list[dict]:
        global _conn
        if _conn is None:
            _conn = _make_connection()
        start = time.perf_counter()
        try:
            result = _conn.execute(sql, params or [])
            rows = result.fetchall()
            columns = [desc[0] for desc in result.description]
            duration = time.perf_counter() - start
            if duration > SLOW_QUERY_THRESHOLD_S:
                log.warning("Slow DuckDB query (%.2fs): %s", duration, sql[:200])
            return [dict(zip(columns, row)) for row in rows]
        except Exception:
            # Reset connection on error so next request gets a fresh one
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
            raise

    return await loop.run_in_executor(None, _run)


async def verify() -> bool:
    """Quick liveness check used by /health and the CI deploy script."""
    try:
        rows = await execute_query("SELECT ST_AsText(ST_Point(36.82, -1.29)) AS pt")
        return bool(rows and "POINT" in rows[0]["pt"])
    except Exception as exc:
        log.error("DuckDB verification failed: %s", exc)
        return False
