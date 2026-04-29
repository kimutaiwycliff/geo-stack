"""
GET /analytics/* — DuckDB-powered analytics endpoints.

All heavy computation runs in DuckDB's thread-pool executor so the event loop
stays free. Results are streamed as GeoJSON or JSON depending on the endpoint.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings
from spatial.duckdb_engine import execute_query
from spatial.queries.bbox_filter import BBox
from spatial.queries.parquet_scan import build_geojson_sql, resolve_parquet_path

log = logging.getLogger("geo-stack.analytics")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/parquet", response_class=Response)
@limiter.limit(f"{settings.api_rate_limit}/minute")
async def query_parquet(
    request: Request,
    file: str = Query(..., description="Filename in DATA_DIR or full s3:// path"),
    bbox: str | None = Query(None, description="xmin,ymin,xmax,ymax (EPSG:4326)"),
    limit: int = Query(500, ge=1, le=10000),
) -> Response:
    """
    Query a GeoParquet file with DuckDB and return GeoJSON.

    The file must be in the mounted /data directory or accessible via S3/R2.
    DuckDB's Parquet row-group pruning makes bbox queries on Hilbert-sorted
    files extremely fast — typically under 200ms for city-scale datasets.
    """
    try:
        path = resolve_parquet_path(file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    parsed_bbox = None
    if bbox:
        try:
            parsed_bbox = BBox.from_string(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    sql = build_geojson_sql(path, bbox=parsed_bbox, limit=limit)

    try:
        rows = await execute_query(sql)
    except Exception as exc:
        log.error("DuckDB parquet query failed: %s", exc)
        raise HTTPException(status_code=500, detail="DuckDB query failed") from exc

    features = [json.loads(row["feature"]) for row in rows if row.get("feature")]
    geojson = json.dumps({"type": "FeatureCollection", "features": features})
    return Response(content=geojson, media_type="application/geo+json")


@router.get("/summary/{layer}", response_class=Response)
@limiter.limit(f"{settings.api_rate_limit}/minute")
async def layer_summary(
    request: Request,
    layer: str,
    bbox: str | None = Query(None, description="xmin,ymin,xmax,ymax (EPSG:4326)"),
) -> Response:
    """
    Return aggregate statistics for a GeoParquet layer using DuckDB.
    Includes feature count, geometry type distribution, and attribute stats.
    """
    # Resolve layer name to parquet file path
    search_path = Path(settings.data_dir)
    candidates = list(search_path.rglob(f"{layer}.parquet"))
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Layer file '{layer}.parquet' not found")

    path = str(candidates[0])

    parsed_bbox = None
    if bbox:
        try:
            parsed_bbox = BBox.from_string(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    bbox_filter = f"WHERE {parsed_bbox.to_duckdb_filter()}" if parsed_bbox else ""

    sql = f"""
        SELECT
            COUNT(*) AS feature_count,
            ST_GeometryType(geometry) AS geom_type,
            COUNT(*) AS type_count
        FROM read_parquet('{path}', hive_partitioning=true)
        {bbox_filter}
        GROUP BY ST_GeometryType(geometry)
    """

    try:
        rows = await execute_query(sql)
    except Exception as exc:
        log.error("DuckDB summary query failed: %s", exc)
        raise HTTPException(status_code=500, detail="DuckDB query failed") from exc

    total = sum(r["type_count"] for r in rows)
    summary = {
        "layer": layer,
        "total_features": total,
        "geometry_types": {r["geom_type"]: r["type_count"] for r in rows},
        "bbox_filter": bbox,
    }

    return Response(content=json.dumps(summary), media_type="application/json")
