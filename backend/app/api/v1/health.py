"""Health and readiness check endpoints."""

from fastapi import APIRouter
from app.core.config import settings
from app.core.database import check_db_connection
from app.core.redis import check_redis_connection
from app.schemas.health import DetailedHealthResponse, HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Basic health probe")
async def get_health() -> HealthResponse:
    """Return basic health status satisfying Phase 1 specification."""
    return HealthResponse(status="ok")


@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    summary="Detailed health and service probe",
)
async def get_detailed_health() -> DetailedHealthResponse:
    """Return detailed health report checking database and cache connections."""
    db_connected = await check_db_connection()
    redis_connected = await check_redis_connection()

    overall_status = "ok" if (db_connected and (redis_connected or not settings.REDIS_URL)) else "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        app=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        database="connected" if db_connected else "disconnected",
        redis=("connected" if redis_connected else "disconnected") if settings.REDIS_URL else "disabled",
        version="1.0.0",
    )
