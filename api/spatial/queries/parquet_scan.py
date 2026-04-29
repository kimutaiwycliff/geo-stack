"""DuckDB read_parquet helpers — build SQL for scanning local or R2-hosted files."""

import json
import logging
from pathlib import Path

from config import settings
from spatial.queries.bbox_filter import BBox

log = logging.getLogger("geo-stack.parquet")


def resolve_parquet_path(filename: str) -> str:
    """
    Resolve a filename to a full read_parquet() path.
    Supports:
      - Local file in DATA_DIR (e.g. 'nairobi_wards.parquet')
      - R2 path prefixed with 's3://' (used when R2_PUBLIC_URL is set)
      - Absolute path (for scripts)
    """
    if filename.startswith("s3://") or filename.startswith("https://"):
        return filename

    local = Path(settings.data_dir) / filename
    if local.exists():
        return str(local)

    # Try subdirectories
    for match in Path(settings.data_dir).rglob(filename):
        return str(match)

    # Fall back to R2 if configured
    if settings.r2_bucket_name and settings.r2_access_key:
        return f"s3://{settings.r2_bucket_name}/{filename}"

    raise FileNotFoundError(f"Cannot resolve parquet file: {filename!r}")


def build_bbox_scan_sql(
    parquet_path: str,
    bbox: BBox | None = None,
    columns: list[str] | None = None,
    limit: int = 1000,
    geom_col: str = "geometry",
) -> str:
    """
    Build a DuckDB SQL query that reads a GeoParquet file with optional bbox filter.

    Uses DuckDB's native Parquet pushdown: if the file has bbox_xmin/bbox_xmax/bbox_ymin/bbox_ymax
    columns (added by optimize_parquet.py), DuckDB will skip row groups outside the bbox
    before touching the geometry column — orders-of-magnitude faster on large files.
    """
    col_expr = ", ".join(columns) if columns else "*"

    if bbox:
        # Coarse filter on pre-computed bbox columns (row-group skip)
        bbox_prefilter = (
            f"bbox_xmin <= {bbox.xmax} AND bbox_xmax >= {bbox.xmin} "
            f"AND bbox_ymin <= {bbox.ymax} AND bbox_ymax >= {bbox.ymin}"
        )
        # Fine spatial filter on actual geometry
        geom_filter = bbox.to_duckdb_filter(geom_col)
        where_clause = f"WHERE ({bbox_prefilter}) AND {geom_filter}"
    else:
        where_clause = ""

    return f"""
        SELECT {col_expr}
        FROM read_parquet('{parquet_path}', hive_partitioning=true)
        {where_clause}
        LIMIT {limit}
    """.strip()


def build_geojson_sql(parquet_path: str, bbox: BBox | None = None, limit: int = 1000) -> str:
    """
    Build SQL that reads a GeoParquet file and returns rows as GeoJSON Feature strings.
    DuckDB spatial extension provides ST_AsGeoJSON() for WKB geometry.
    """
    bbox_filter = f"AND {bbox.to_duckdb_filter()}" if bbox else ""
    return f"""
        SELECT
            json_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(geometry)::JSON,
                'properties', (
                    SELECT json_object(k, v)
                    FROM unnest(map_keys(row), map_values(row)) AS t(k, v)
                    WHERE k NOT IN ('geometry', 'bbox_xmin', 'bbox_xmax', 'bbox_ymin', 'bbox_ymax')
                )
            ) AS feature
        FROM read_parquet('{parquet_path}', hive_partitioning=true)
        WHERE geometry IS NOT NULL {bbox_filter}
        LIMIT {limit}
    """.strip()
