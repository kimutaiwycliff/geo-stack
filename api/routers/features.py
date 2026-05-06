"""GET /features/{layer} — GeoJSON FeatureCollection from PostGIS."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from dependencies import PostGIS
from spatial.queries.bbox_filter import BBox

log = logging.getLogger("geo-stack.features")

router = APIRouter()

# Allowlist of queryable layers (schema.table). Prevents SQL injection via layer name.
ALLOWED_LAYERS: dict[str, tuple[str, str]] = {
    "parcels":            ("geo", "parcels"),
    "boundaries":         ("geo", "boundaries"),
    "points_of_interest": ("geo", "points_of_interest"),
    "administration":     ("geo", "adm_adm_1"),
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
    limit: int = Query(default=500, ge=1, le=5000),
) -> Response:
    """
    Return a GeoJSON FeatureCollection from a PostGIS layer.

    - **layer**: one of `parcels`, `boundaries`, `points_of_interest`
    - **bbox**: optional spatial filter
    - **limit**: max features returned (default 500)
    """
    if layer not in ALLOWED_LAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer}' not found. Available: {list(ALLOWED_LAYERS.keys())}",
        )

    schema, table = ALLOWED_LAYERS[layer]

    try:
        parsed_bbox = BBox.from_string(bbox) if bbox else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed_bbox:
        where_clause = (
            f"WHERE geom && ST_MakeEnvelope("
            f"{parsed_bbox.xmin}, {parsed_bbox.ymin}, "
            f"{parsed_bbox.xmax}, {parsed_bbox.ymax}, 4326)"
        )
    else:
        where_clause = ""

    # ST_AsGeoJSON returns the geometry as a JSON string.
    # row_to_json strips the geometry column so it becomes properties.
    sql = f"""
        SELECT
            jsonb_build_object(
                'type', 'Feature',
                'id', id,
                'geometry', ST_AsGeoJSON(geom)::jsonb,
                'properties', (to_jsonb(t.*) - 'geom' - 'id')
            ) AS feature
        FROM {schema}.{table} t
        {where_clause}
        ORDER BY id
        LIMIT {limit}
    """

    rows = await conn.fetch(sql)
    features = [json.loads(row["feature"]) for row in rows]

    geojson = json.dumps({
        "type": "FeatureCollection",
        "features": features,
    })

    return Response(content=geojson, media_type="application/geo+json")
