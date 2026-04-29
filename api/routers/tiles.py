"""
GET /tiles/{source}/{z}/{x}/{y}.mvt — proxy to Martin with caching headers.

This endpoint exists so the frontend only has one API base URL to configure.
In production, Caddy can be configured to route /tiles directly to Martin
for zero-overhead access.
"""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Response

from config import settings

log = logging.getLogger("geo-stack.tiles")
router = APIRouter()

# Tile cache headers: tiles are valid for 1 hour in CDN, 5 mins in browser.
CACHE_CONTROL = "public, max-age=300, s-maxage=3600"


@router.get("/{source}/{z}/{x}/{y}.mvt")
async def proxy_tile(source: str, z: int, x: int, y: int) -> Response:
    """
    Proxy an MVT tile request to Martin.

    - **source**: Martin source ID (matches table names in geo schema, e.g. 'geo.parcels')
    - **z/x/y**: tile coordinates
    """
    if z < 0 or z > 22:
        raise HTTPException(status_code=400, detail="Zoom level must be between 0 and 22")

    martin_url = f"{settings.martin_url}/{source}/{z}/{x}/{y}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            upstream = await client.get(martin_url)
        except httpx.RequestError as exc:
            log.error("Martin request failed: %s", exc)
            raise HTTPException(status_code=503, detail="Tile server unavailable") from exc

    if upstream.status_code == 204:
        # Empty tile — still valid, just no features in this tile
        return Response(status_code=204, headers={"Cache-Control": CACHE_CONTROL})

    if upstream.status_code != 200:
        raise HTTPException(
            status_code=upstream.status_code,
            detail=f"Martin returned {upstream.status_code}",
        )

    return Response(
        content=upstream.content,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": CACHE_CONTROL},
    )
