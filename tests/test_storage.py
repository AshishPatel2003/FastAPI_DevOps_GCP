"""Tests for storage routes."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_public_success(client: AsyncClient, user_token_headers: dict, mocker):
    """Test uploading to the public bucket."""
    # Mock the GCS service to avoid real uploads during testing
    mocker.patch("app.api.v1.storage.gcs_service.upload_public", return_value="https://storage.googleapis.com/test-bucket/test.txt")

    files = {"file": ("test.txt", b"Hello, World!", "text/plain")}
    response = await client.post("/api/v1/storage/public/upload", files=files, headers=user_token_headers)

    assert response.status_code == 200
    assert "url" in response.json()


@pytest.mark.asyncio
async def test_generate_signed_url_success(client: AsyncClient, user_token_headers: dict, test_user, mocker):
    """Test generating a signed URL for a file owned by the user."""
    mock_url = "https://storage.googleapis.com/test-private/test.txt?GoogleAccessId=..."
    mocker.patch("app.api.v1.storage.gcs_service.file_exists", return_value=True)
    mocker.patch("app.api.v1.storage.gcs_service.generate_signed_url", return_value=mock_url)

    path = f"users/{test_user.id}/test.txt"
    response = await client.get(f"/api/v1/storage/private/{path}", headers=user_token_headers)

    assert response.status_code == 200
    assert "signed_url" in response.json()
    assert response.json()["signed_url"] == mock_url


@pytest.mark.asyncio
async def test_generate_signed_url_forbidden(client: AsyncClient, user_token_headers: dict, test_user, mocker):
    """Test user cannot access another user's private file."""
    other_user_path = "users/123e4567-e89b-12d3-a456-426614174000/test.txt"
    response = await client.get(f"/api/v1/storage/private/{other_user_path}", headers=user_token_headers)

    assert response.status_code == 403
