"""
FastAPI Application Entrypoint.

Configures the FastAPI application, middleware, lifecycle events (lifespan),
and includes all routers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import api_router
from app.api.ws import ws_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import verify_db_connection
from app.middleware.logging_middleware import LoggingMiddleware
from app.services.redis_service import close_redis, init_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.

    Executed before the application starts taking requests (startup),
    and after it finishes handling requests (shutdown).
    """
    # ------------------------------------------------------------------
    # Startup Events
    # ------------------------------------------------------------------
    configure_logging()
    logger.info("Application starting up...", extra={"env": settings.APP_ENV})

    # Verify DB connectivity (Optional: create first superuser here if needed)
    db_ok = await verify_db_connection()
    if not db_ok:
        logger.warning("Database connection failed during startup. Endpoints may return 500s.")

    # Initialize Redis connection pool
    try:
        await init_redis()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize Redis pool", extra={"error": str(exc)})

    # Yield control to FastAPI to start serving requests
    yield

    # ------------------------------------------------------------------
    # Shutdown Events
    # ------------------------------------------------------------------
    logger.info("Application shutting down...")

    # Close Redis connection pool
    await close_redis()

    # DB engine (SQLAlchemy) handles its own pool cleanup on exit,
    # but could explicitly dispose if required: await engine.dispose()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    # Note: ORJSONResponse is generally faster than the default JSONResponse
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise FastAPI Application with GCP Integrations",
        docs_url=settings.docs_url,     # None in production
        redoc_url=settings.redoc_url,   # None in production
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
    )

    # ------------------------------------------------------------------
    # Middleware Setup
    # ------------------------------------------------------------------
    # Request logging (must be added before CORS so it logs CORS preflights too)
    app.add_middleware(LoggingMiddleware)

    # CORS
    if settings.ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.ALLOWED_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ------------------------------------------------------------------
    # Routes Setup
    # ------------------------------------------------------------------
    # Add v1 REST API
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Add WebSocket API
    app.include_router(ws_router)

    return app


# The ASGI application instance (used by uvicorn)
app = create_app()
