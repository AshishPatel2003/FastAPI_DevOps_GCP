import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings
from app.db.base import Base

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# (Skipped in tests or if logging config is disabled)
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# Import all models here so Alembic can detect schemas
# Base must be imported after models
from app.models import *  # noqa: F401, F403

target_metadata = Base.metadata


def get_url() -> str:
    """
    Get the database URL.

    Falls back to the Alembic config if DATABASE_URL is not set
    (which shouldn't happen with our .env setup).
    """
    # Prefer the application's environment-aware settings
    url = settings.DATABASE_URL

    # For Cloud Run, if a Cloud SQL instance is defined, Alembic needs to connect
    # via the unix socket, just like the application engine does.
    if settings.CLOUD_SQL_INSTANCE and "cloudsql" not in url:
        socket_path = f"/cloudsql/{settings.CLOUD_SQL_INSTANCE}"
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}host={socket_path}"

    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run the actual migration using the connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Compare types (e.g. String(50) -> String(100))
        compare_type=True,
        # Compare server defaults
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = create_async_engine(get_url(), poolclass=None)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
