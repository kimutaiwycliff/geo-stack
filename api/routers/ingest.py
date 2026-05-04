"""
Ingest router — import GeoJSON features into staging.raw_features.

Accepts features already converted to GeoJSON (conversion happens client-side
in the browser). Uses Server-Sent Events to stream insert progress back so the
UI can show a real-time progress bar.

Endpoints:
  POST /ingest/features   — stream-insert GeoJSON features (SSE response)
  GET  /ingest/layers     — list layers currently in staging.raw_features
  DELETE /ingest/layer/{name} — clear a staging layer
"""

import json
import logging
import re
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from spatial.postgis_engine import get_postgis_pool

router = APIRouter()
log = logging.getLogger("geo-stack.ingest")

MAX_FEATURES = 100_000
BATCH_SIZE = 500

VALID_GEOM_TYPES = {
    "Point", "MultiPoint",
    "LineString", "MultiLineString",
    "Polygon", "MultiPolygon",
    "GeometryCollection",
}


class IngestRequest(BaseModel):
    source: str        # original filename
    layer_name: str    # user-supplied name for this import
    features: list[dict]  # GeoJSON Feature objects

    @field_validator("layer_name")
    @classmethod
    def sanitise_layer_name(cls, v: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_]", "_", v.lower().strip())[:64]
        if not cleaned:
            raise ValueError("layer_name cannot be empty")
        return cleaned

    @field_validator("source")
    @classmethod
    def sanitise_source(cls, v: str) -> str:
        return v.strip()[:255]


@router.post("/features")
async def ingest_features(req: IngestRequest):
    """
    Insert GeoJSON features into staging.raw_features, streaming progress via SSE.

    Response is text/event-stream. Each event is a JSON object:
      { inserted, total, pct, skipped, elapsed_s }
    Final event adds { done: true, errors: [...] }.

    All geometries are forced to 2D and assumed EPSG:4326.
    Invalid or null geometries are counted as skipped.
    """
    if not req.features:
        raise HTTPException(400, "No features provided")
    if len(req.features) > MAX_FEATURES:
        raise HTTPException(
            400,
            f"Max {MAX_FEATURES:,} features per upload — got {len(req.features):,}. "
            "Use scripts/load_supabase.sh for larger datasets.",
        )

    pool = await get_postgis_pool()
    total = len(req.features)

    async def _stream():
        inserted = 0
        skipped = 0
        errors: list[str] = []
        start = time.perf_counter()

        async with pool.acquire() as conn:
            for batch_start in range(0, total, BATCH_SIZE):
                batch = req.features[batch_start : batch_start + BATCH_SIZE]
                rows = []
                for feat in batch:
                    geom = feat.get("geometry")
                    if not geom or geom.get("type") not in VALID_GEOM_TYPES:
                        skipped += 1
                        continue
                    rows.append((
                        req.source,
                        req.layer_name,
                        json.dumps(feat.get("properties") or {}),
                        json.dumps(geom),
                    ))

                if rows:
                    try:
                        await conn.executemany(
                            """
                            INSERT INTO staging.raw_features
                                (source, layer_name, properties, geom)
                            VALUES (
                                $1, $2, $3::jsonb,
                                ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))
                            )
                            """,
                            rows,
                        )
                        inserted += len(rows)
                    except Exception as exc:
                        err_msg = str(exc)[:300]
                        errors.append(err_msg)
                        skipped += len(rows)
                        log.error("Ingest batch offset=%d failed: %s", batch_start, exc)

                elapsed = time.perf_counter() - start
                pct = round(inserted / total * 100, 1) if total else 0
                payload = {
                    "inserted": inserted,
                    "total": total,
                    "pct": pct,
                    "skipped": skipped,
                    "elapsed_s": round(elapsed, 1),
                }
                yield f"data: {json.dumps(payload)}\n\n"

        elapsed = time.perf_counter() - start
        final = {
            "done": True,
            "inserted": inserted,
            "total": total,
            "skipped": skipped,
            "errors": errors[:5],
            "elapsed_s": round(elapsed, 1),
        }
        log.info(
            "Ingest complete: layer=%s inserted=%d/%d skipped=%d elapsed=%.1fs",
            req.layer_name, inserted, total, skipped, elapsed,
        )
        yield f"data: {json.dumps(final)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx/Render response buffering
        },
    )


@router.get("/layers")
async def list_staging_layers():
    """List all layers currently in staging.raw_features with feature counts."""
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                layer_name,
                source,
                COUNT(*)               AS feature_count,
                MAX(imported_at)       AS last_imported,
                ST_AsGeoJSON(ST_Extent(geom))::jsonb AS bbox_geojson
            FROM staging.raw_features
            GROUP BY layer_name, source
            ORDER BY last_imported DESC
            LIMIT 50
        """)
    return [
        {
            "layer_name": r["layer_name"],
            "source": r["source"],
            "feature_count": r["feature_count"],
            "last_imported": r["last_imported"].isoformat() if r["last_imported"] else None,
            "bbox": r["bbox_geojson"],
        }
        for r in rows
    ]


@router.delete("/layer/{layer_name}")
async def delete_staging_layer(layer_name: str):
    """Remove all features for a layer from staging.raw_features."""
    clean = re.sub(r"[^a-z0-9_]", "_", layer_name.lower())
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM staging.raw_features WHERE layer_name = $1", clean
        )
    deleted = int(result.split()[-1])
    log.info("Deleted staging layer: %s (%d rows)", clean, deleted)
    return {"deleted": deleted, "layer": clean}
