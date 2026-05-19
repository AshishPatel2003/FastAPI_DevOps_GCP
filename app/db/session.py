"""
SQLAlchemy async session factory.

Cloud Run + Cloud SQL connection pattern:
- Production: uses Unix socket via /cloudsql/<INSTANCE_CONNECTION_NAME>
- Local dev: uses standard TCP connection (DATABASE_URL in .env)

The engine and session factory are module-level singletons.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _build_database_url() -> str:
    """
    Build the effective database URL.

    On Cloud Run, if a CLOUD_SQL_INSTANCE is configured, append the Unix
    socket query parameter so asyncpg connects through the Cloud SQL Auth Proxy
    socket that Cloud Run injects at runtime.
    """
    url = settings.DATABASE_URL

    # Cloud Run Cloud SQL unix socket pattern
    # asyncpg supports the ?host=/cloudsql/... syntax
    if settings.CLOUD_SQL_INSTANCE and "cloudsql" not in url:
        socket_path = f"/cloudsql/{settings.CLOUD_SQL_INSTANCE}"
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}host={socket_path}"
        logger.info(
            "Using Cloud SQL unix socket",
            extra={"instance": settings.CLOUD_SQL_INSTANCE},
        )

    return url


# Create the async engine — shared across the app lifetime
engine = create_async_engine(
    _build_database_url(),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,           # Detect stale connections before use
    pool_recycle=3600,            # Recycle connections every hour
    echo=settings.DEBUG,          # Log SQL in debug mode only
)

# Session factory — use this to create per-request sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,       # Prevent lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session per request.

    Usage in route:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
