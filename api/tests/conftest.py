"""
Test fixtures for geo-stack API.

Integration tests use testcontainers-python to spin up a real PostGIS instance.
Unit tests mock the DB connections so they run without Docker.
"""

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Point to a test database — overridden to testcontainer in integration tests
os.environ.setdefault("DATABASE_URL", "postgresql://geouser:testpass@localhost:5432/geodata_test")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("DATA_DIR", "/tmp/geo-stack-test-data")

from main import app  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    """HTTP client wired directly to the ASGI app — no real server needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c
