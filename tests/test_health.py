"""Tests for the health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient, mocker):
    """
    Test the health check endpoint returns 200 OK and expected structure.
    """
    # Mock verify_db_connection / Redis ping to succeed for the health check
    # The client fixture already mocks the DB dependency for routes,
    # but the health check instantiates AsyncSessionLocal directly.
    # We patch the health route's session logic here just to prevent it from
    # trying to connect to the real postgres DB.
    mocker.patch("app.api.v1.health.AsyncSessionLocal", autospec=True)

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("healthy", "degraded")
    assert "timestamp" in data
    assert "environment" in data
    assert "app_version" in data
    assert "components" in data
    assert "database" in data["components"]
    assert "redis" in data["components"]
