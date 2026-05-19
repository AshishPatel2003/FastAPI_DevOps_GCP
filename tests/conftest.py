"""Pytest configuration and fixtures."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_redis_client
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.main import app
from app.models.user import User


# =============================================================================
# Event Loop
# =============================================================================

@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create an async SQLite engine for testing."""
    # Use in-memory SQLite for fast testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scoped session."""
    session_maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
        # Clear tables after each test
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


# =============================================================================
# Application Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, mocker: Any) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an AsyncClient for FastAPI testing.

    Overrides the get_db dependency to use the test SQLite session.
    Mocks out Redis to prevent tests from needing a real Redis server.
    """
    app.dependency_overrides[get_db] = lambda: db_session

    # Mock Redis connection pool for testing
    mock_redis = mocker.AsyncMock()
    # Ensure token blacklist exists() returns 0 (not blacklisted)
    mock_redis.exists.return_value = 0
    app.dependency_overrides[get_redis_client] = lambda: mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# User Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a standard test user in the database."""
    from app.core.security import hash_password

    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        full_name="Test User",
        hashed_password=hash_password("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def super_user(db_session: AsyncSession) -> User:
    """Create a superuser in the database."""
    from app.core.security import hash_password

    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin User",
        hashed_password=hash_password("admin123"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def user_token_headers(test_user: User) -> dict[str, str]:
    """Return authorization headers for the standard user."""
    access_token = create_access_token(subject=str(test_user.id))
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def super_user_token_headers(super_user: User) -> dict[str, str]:
    """Return authorization headers for the superuser."""
    access_token = create_access_token(subject=str(super_user.id))
    return {"Authorization": f"Bearer {access_token}"}
