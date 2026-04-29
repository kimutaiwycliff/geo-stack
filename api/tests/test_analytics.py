"""Tests for GET /analytics/* — DuckDB parquet scan endpoints."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock


MOCK_GEOJSON_FEATURE = json.dumps({
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [36.82, -1.29]},
    "properties": {"name": "Nairobi CBD"},
})


@pytest.mark.asyncio
async def test_parquet_missing_file_returns_404(client):
    response = await client.get("/analytics/parquet?file=doesnotexist.parquet")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_parquet_invalid_bbox_returns_400(client, tmp_path):
    parquet = tmp_path / "test.parquet"
    parquet.write_bytes(b"placeholder")  # DuckDB will reject this, but 400 comes first

    with patch("routers.analytics.resolve_parquet_path", return_value=str(parquet)):
        response = await client.get(
            f"/analytics/parquet?file=test.parquet&bbox=invalid"
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_parquet_returns_geojson(client):
    mock_rows = [{"feature": MOCK_GEOJSON_FEATURE}]

    with (
        patch("routers.analytics.resolve_parquet_path", return_value="/data/test.parquet"),
        patch("routers.analytics.execute_query", new_callable=AsyncMock, return_value=mock_rows),
    ):
        response = await client.get("/analytics/parquet?file=test.parquet")

    assert response.status_code == 200
    assert "application/geo+json" in response.headers["content-type"]
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["type"] == "Feature"


@pytest.mark.asyncio
async def test_parquet_bbox_filter_passed_to_duckdb(client):
    mock_rows = [{"feature": MOCK_GEOJSON_FEATURE}]

    with (
        patch("routers.analytics.resolve_parquet_path", return_value="/data/test.parquet"),
        patch("routers.analytics.execute_query", new_callable=AsyncMock, return_value=mock_rows) as mock_exec,
    ):
        response = await client.get(
            "/analytics/parquet?file=test.parquet&bbox=36.65,-1.44,37.10,-1.16"
        )

    assert response.status_code == 200
    # Verify the SQL passed to DuckDB contains a spatial filter
    call_args = mock_exec.call_args[0][0]
    assert "ST_Intersects" in call_args or "bbox_xmin" in call_args
