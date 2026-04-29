"""Tests for GET /features/{layer} — GeoJSON from PostGIS."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_rows(n: int = 2) -> list[MagicMock]:
    """Build fake asyncpg Record-like objects."""
    rows = []
    for i in range(n):
        row = MagicMock()
        row.__getitem__ = lambda self, key: json.dumps({
            "type": "Feature",
            "id": i,
            "geometry": {"type": "Point", "coordinates": [36.82, -1.29]},
            "properties": {"name": f"Feature {i}"},
        })
        rows.append(row)
    return rows


@pytest.mark.asyncio
async def test_features_returns_geojson(client):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=_make_mock_rows(3))

    with patch("dependencies.get_postgis_pool") as mock_pool:
        pool = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        response = await client.get("/features/points_of_interest")

    assert response.status_code == 200
    assert "application/geo+json" in response.headers["content-type"]
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert isinstance(body["features"], list)


@pytest.mark.asyncio
async def test_features_unknown_layer_returns_404(client):
    response = await client.get("/features/nonexistent_layer")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_features_invalid_bbox_returns_400(client):
    mock_conn = AsyncMock()
    with patch("dependencies.get_postgis_pool") as mock_pool:
        pool = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        response = await client.get("/features/boundaries?bbox=notabbox")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_features_bbox_filter_applied(client):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=_make_mock_rows(1))

    with patch("dependencies.get_postgis_pool") as mock_pool:
        pool = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        response = await client.get(
            "/features/boundaries?bbox=36.65,-1.44,37.10,-1.16&limit=10"
        )

    assert response.status_code == 200
    # Verify fetch was called (SQL was generated and executed)
    mock_conn.fetch.assert_called_once()
