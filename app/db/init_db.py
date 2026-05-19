"""
Database initialization helpers.

Used at application startup to verify connectivity and optionally
run lightweight seed operations.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import engine

logger = get_logger(__name__)


async def verify_db_connection() -> bool:
    """
    Verify that the database is reachable and responsive.

    Returns:
        True if the database ping succeeds, False otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Database connection failed", extra={"error": str(exc)})
        return False


async def create_first_superuser(db: AsyncSession) -> None:
    """
    Create the initial superuser if none exists.

    This is a convenience for fresh deployments. In production, seed via
    Alembic data migrations instead.
    """
    from app.core.config import settings
    from app.core.security import hash_password
    from app.crud.user import user_crud
    from app.schemas.user import UserCreate

    # Only create in non-production or when explicitly enabled
    if settings.is_production:
        return

    existing = await user_crud.get_by_email(db, email="admin@example.com")
    if existing:
        return

    superuser = UserCreate(
        email="admin@example.com",
        password="admin123",
        full_name="System Administrator",
    )
    await user_crud.create(db, obj_in=superuser, is_superuser=True)
    logger.info("Default superuser created", extra={"email": superuser.email})
