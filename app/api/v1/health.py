"""
Health Check Endpoints.

Provides a comprehensive health check that verifies:
- Application is running
- Database connectivity
- Redis connectivity
- Current environment and version info

Used by load balancers, monitoring systems, and CI/CD pipelines.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.redis_service import get_redis

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


class ComponentStatus(BaseModel):
    """Status of a single infrastructure component."""
    status: str        # "ok" | "degraded" | "unavailable"
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    """Full health check response."""
    status: str        # "healthy" | "degraded" | "unhealthy"
    timestamp: str
    environment: str
    app_version: str
    components: dict[str, ComponentStatus]


@router.get("", response_model=HealthResponse, summary="Application Health Check")
async def health_check() -> HealthResponse:
    """
    Comprehensive health check endpoint.

    Returns the operational status of the application and all
    dependent infrastructure components (database, Redis cache).

    This endpoint does NOT require authentication so it can be used
    by load balancers and uptime monitors.
    """
    components: dict[str, ComponentStatus] = {}
    overall_healthy = True

    # ------------------------------------------------------------------
    # Database Check
    # ------------------------------------------------------------------
    try:
        start = datetime.now(UTC)
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency = (datetime.now(UTC) - start).total_seconds() * 1000
        components["database"] = ComponentStatus(
            status="ok",
            latency_ms=round(latency, 2),
            detail="PostgreSQL connection verified",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health check failed", extra={"error": str(exc)})
        components["database"] = ComponentStatus(
            status="unavailable",
            detail=str(exc) if settings.DEBUG else "Connection failed",
        )
        overall_healthy = False

    # ------------------------------------------------------------------
    # Redis Check
    # ------------------------------------------------------------------
    try:
        start = datetime.now(UTC)
        redis = get_redis()
        await redis.ping()
        latency = (datetime.now(UTC) - start).total_seconds() * 1000
        components["redis"] = ComponentStatus(
            status="ok",
            latency_ms=round(latency, 2),
            detail="Redis connection verified",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis health check failed", extra={"error": str(exc)})
        components["redis"] = ComponentStatus(
            status="unavailable",
            detail=str(exc) if settings.DEBUG else "Connection failed",
        )
        overall_healthy = False

    return HealthResponse(
        status="healthy" if overall_healthy else "degraded",
        timestamp=datetime.now(UTC).isoformat(),
        environment=settings.APP_ENV,
        app_version=settings.APP_VERSION,
        components=components,
    )
