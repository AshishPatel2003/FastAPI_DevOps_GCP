"""Tests for authentication routes."""

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test public user registration."""
    payload = {
        "email": "newuser@example.com",
        "password": "password123",
        "full_name": "New User"
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    """Test registration fails with duplicate email."""
    payload = {
        "email": test_user.email,
        "password": "password123",
        "full_name": "Duplicate"
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    """Test login with correct credentials."""
    payload = {
        "username": test_user.email,
        "password": "password123",
    }
    # OAuth2PasswordRequestForm expects x-www-form-urlencoded
    response = await client.post("/api/v1/auth/login", data=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    """Test login with incorrect credentials."""
    payload = {
        "username": test_user.email,
        "password": "wrongpassword",
    }
    response = await client.post("/api/v1/auth/login", data=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, test_user: User, user_token_headers: dict):
    """Test accessing protected route with token."""
    response = await client.get("/api/v1/users/me", headers=user_token_headers)
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    """Test accessing protected route without token."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
