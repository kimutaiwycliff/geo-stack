"""GET /features/{layer} — GeoJSON FeatureCollection from PostGIS."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from dependencies import PostGIS
from spatial.queries.bbox_filter import BBox

log = logging.getLogger("geo-stack.features")

router = APIRouter()

# Allowlist of queryable layers (schema, table, name_col).
# name_col is the text column used by the ?q= search filter.
# Prevents SQL injection via layer name — never build these from user input.
ALLOWED_LAYERS: dict[str, tuple[str, str, str | None]] = {
    "parcels":            ("geo", "parcels",            "owner_name"),
    "boundaries":         ("geo", "boundaries",         "name"),
    "points_of_interest": ("geo", "points_of_interest", "name"),
    "administration":     ("geo", "adm_adm_1",          "name_1"),
}


@router.get("/{layer}", response_class=Response)
async def get_features(
    layer: str,
    conn: PostGIS,
    bbox: str | None = Query(
        default=None,
        description="Bounding box: xmin,ymin,xmax,ymax (EPSG:4326)",
        example="36.65,-1.44,37.10,-1.16",
    ),
    q: str | None = Query(
        default=None,
        description="Filter by name (case-insensitive, partial match). "
                    "Searches the name column for the layer: "
                    "administration→name_1, boundaries→name, points_of_interest→name.",
        example="Nairobi",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
) -> Response:
    """
    Return a GeoJSON FeatureCollection from a PostGIS layer.

    - **layer**: one of `parcels`, `boundaries`, `points_of_interest`, `administration`
    - **bbox**: optional spatial filter
    - **q**: optional name search (e.g. `?q=Nairobi` on the administration layer)
    - **limit**: max features returned (default 500)
    """
    if layer not in ALLOWED_LAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer}' not found. Available: {list(ALLOWED_LAYERS.keys())}",
        )

    schema, table, name_col = ALLOWED_LAYERS[layer]

    try:
        parsed_bbox = BBox.from_string(bbox) if bbox else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Build WHERE clause from bbox and optional name filter.
    # q is passed as a positional parameter ($1) — never interpolated — to prevent injection.
    conditions: list[str] = []
    params: list = []

    if parsed_bbox:
        conditions.append(
            f"geom && ST_MakeEnvelope("
            f"{parsed_bbox.xmin}, {parsed_bbox.ymin}, "
            f"{parsed_bbox.xmax}, {parsed_bbox.ymax}, 4326)"
        )

    if q and name_col:
        params.append(f"%{q}%")
        conditions.append(f"{name_col} ILIKE ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Use COALESCE(id, ...) so layers with non-standard primary keys still work.
    # Martin names its vector layer "schema.table" — strip schema for the feature id.
    sql = f"""
        SELECT
            jsonb_build_object(
                'type', 'Feature',
                'id', t.id,
                'geometry', ST_AsGeoJSON(t.geom)::jsonb,
                'properties', (to_jsonb(t.*) - 'geom' - 'id')
            ) AS feature
        FROM {schema}.{table} t
        {where_clause}
        ORDER BY t.id
        LIMIT {limit}
    """

    try:
        rows = await conn.fetch(sql, *params)
    except Exception as exc:
        log.error("features query failed for layer=%s: %s", layer, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Query failed for layer '{layer}': {exc}",
        ) from exc

    features = [json.loads(row["feature"]) for row in rows]

    geojson = json.dumps({
        "type": "FeatureCollection",
        "features": features,
    })

    return Response(content=geojson, media_type="application/geo+json")
