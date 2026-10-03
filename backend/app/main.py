"""CartPilot backend FastAPI main application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.shopify import router as shopify_router
from app.api.v1.health import router as health_router
from app.api.v1.pricing import router as pricing_router
from app.api.v1.restock import router as restock_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.actions import router as actions_router
from app.api.v1.listing import router as listing_router
from app.api.v1.promotion import router as promotion_router
from app.api.v1.store import router as store_router
from app.core.config import settings
from app.core.database import close_db_connection
from app.core.redis import close_redis_connection
from app.schemas.health import HealthResponse

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cartpilot")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown procedures."""
    logger.info("Starting %s version=1.0.0 environment=%s", settings.APP_NAME, settings.ENVIRONMENT)
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
    debug=False,
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
app.include_router(shopify_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(pricing_router, prefix="/api/v1")
app.include_router(restock_router, prefix="/api/v1")
app.include_router(orchestration_router, prefix="/api/v1")
app.include_router(store_router, prefix="/api/v1")
app.include_router(promotion_router, prefix="/api/v1")
app.include_router(listing_router, prefix="/api/v1")
app.include_router(actions_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root_info() -> dict:
    """Root info endpoint providing basic application metadata."""
    return {
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "status": "online",
        "docs_url": "/docs",
    }

@app.exception_handler(ConnectionError)
@app.exception_handler(SQLAlchemyError)
async def storage_failure(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("api_storage_failure type=%s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Store data is temporarily unavailable; try again."})

@app.exception_handler(Exception)
async def unexpected_failure(request: Request, exc: Exception) -> JSONResponse:
    logger.error("api_unexpected_failure type=%s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "CartPilot could not complete this request. Please try again."})

@app.middleware("http")
async def safe_error_boundary(request: Request, call_next):
    # Prevent server middleware from re-raising unexpected exceptions into raw logs.
    try:
        return await call_next(request)
    except (SQLAlchemyError, ConnectionError) as exc:
        return await storage_failure(request, exc)
    except Exception as exc:
        return await unexpected_failure(request, exc)
