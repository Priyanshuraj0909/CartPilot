"""CartPilot backend FastAPI main application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.database import close_db_connection
from app.core.redis import close_redis_connection
from app.schemas.health import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cartpilot")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown procedures."""
    logger.info("Starting %s in %s mode...", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    logger.info("Shutting down %s, closing resources...", settings.APP_NAME)
    await close_redis_connection()
    await close_db_connection()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    description="CartPilot - AI Manager for E-Commerce Storefronts",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Root health endpoint specified in Phase 1",
)
async def root_health() -> HealthResponse:
    """Direct root-level health endpoint matching Phase 1 requirement."""
    return HealthResponse(status="ok")


# Mount API routers
app.include_router(health_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root_info() -> dict:
    """Root info endpoint providing basic application metadata."""
    return {
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "status": "online",
        "docs_url": "/docs",
    }
