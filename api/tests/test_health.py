"""Tests for GET /health — liveness and readiness."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_returns_200(client):
    with (
        patch("routers.health.postgis_verify", new_callable=AsyncMock, return_value=True),
        patch("routers.health.duckdb_verify", new_callable=AsyncMock, return_value=True),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgis"] is True
    assert body["duckdb"] is True


@pytest.mark.asyncio
async def test_health_degraded_when_postgis_down(client):
    with (
        patch("routers.health.postgis_verify", new_callable=AsyncMock, return_value=False),
        patch("routers.health.duckdb_verify", new_callable=AsyncMock, return_value=True),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgis"] is False
    assert body["duckdb"] is True
