"""
STAC-compliant catalog endpoints for GeoParquet assets.

SpatioTemporal Asset Catalog (STAC) lets clients discover what data is available
without knowing filenames. This implementation is a lightweight static catalog
built by scanning the DATA_DIR at request time — suitable for datasets up to ~1000 files.

Spec: https://stacspec.org/en/about/stac-spec/
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from config import settings

log = logging.getLogger("geo-stack.stac")
router = APIRouter()

STAC_VERSION = "1.0.0"


def _parquet_to_stac_item(path: Path, collection_id: str) -> dict:
    """Convert a GeoParquet file path to a minimal STAC Item."""
    stat = path.stat()
    rel = path.relative_to(settings.data_dir)
    item_id = path.stem

    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "id": item_id,
        "collection": collection_id,
        "geometry": None,  # Real implementations would read bbox from parquet metadata
        "bbox": None,
        "properties": {
            "datetime": None,
            "title": item_id.replace("_", " ").title(),
            "size_bytes": stat.st_size,
            "path": str(rel),
        },
        "assets": {
            "data": {
                "href": f"{settings.r2_public_url}/{rel}" if settings.r2_public_url else f"/data/{rel}",
                "type": "application/x-parquet",
                "title": "GeoParquet data file",
                "roles": ["data"],
            }
        },
        "links": [],
    }


@router.get("/collections")
async def list_collections() -> Response:
    """
    Return a STAC catalog listing all available GeoParquet collections.
    Collections are discovered by scanning DATA_DIR subdirectories.
    """
    data_path = Path(settings.data_dir)
    if not data_path.exists():
        return Response(
            content=json.dumps({"collections": [], "links": []}),
            media_type="application/json",
        )

    # Each subdirectory that contains .parquet files becomes a collection
    collections = []
    for subdir in sorted(data_path.iterdir()):
        if not subdir.is_dir():
            continue
        parquet_files = list(subdir.glob("*.parquet"))
        if not parquet_files:
            continue
        coll_id = subdir.name
        collections.append({
            "type": "Collection",
            "id": coll_id,
            "stac_version": STAC_VERSION,
            "description": f"GeoParquet dataset: {coll_id}",
            "links": [
                {"rel": "items", "href": f"/stac/collections/{coll_id}/items", "type": "application/geo+json"},
                {"rel": "self", "href": f"/stac/collections/{coll_id}", "type": "application/json"},
            ],
            "item_count": len(parquet_files),
        })

    # Also expose top-level parquet files as a 'root' collection
    root_files = list(data_path.glob("*.parquet"))
    if root_files:
        collections.append({
            "type": "Collection",
            "id": "root",
            "stac_version": STAC_VERSION,
            "description": "GeoParquet files in root data directory",
            "links": [
                {"rel": "items", "href": "/stac/collections/root/items", "type": "application/geo+json"},
            ],
            "item_count": len(root_files),
        })

    result = {
        "type": "Catalog",
        "id": "geo-stack",
        "stac_version": STAC_VERSION,
        "description": "geo-stack GeoParquet data catalog",
        "collections": collections,
        "links": [{"rel": "self", "href": "/stac/collections"}],
    }

    return Response(content=json.dumps(result), media_type="application/json")


@router.get("/collections/{collection_id}/items")
async def list_items(collection_id: str) -> Response:
    """Return STAC Items (GeoJSON FeatureCollection) for a collection."""
    data_path = Path(settings.data_dir)

    if collection_id == "root":
        search_dir = data_path
    else:
        search_dir = data_path / collection_id
        if not search_dir.exists():
            raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")

    parquet_files = sorted(search_dir.glob("*.parquet"))
    if not parquet_files:
        raise HTTPException(status_code=404, detail=f"No items in collection '{collection_id}'")

    items = [_parquet_to_stac_item(f, collection_id) for f in parquet_files]
    result = {
        "type": "FeatureCollection",
        "features": items,
        "links": [
            {"rel": "collection", "href": f"/stac/collections/{collection_id}"},
        ],
    }

    return Response(content=json.dumps(result), media_type="application/geo+json")
