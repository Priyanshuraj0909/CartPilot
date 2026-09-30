"""Health check response models."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Standard health check response model."""

    status: str = Field(default="ok", description="Overall system health status")


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with component status."""

    status: str = Field(default="ok", description="Overall health status")
    app: str = Field(..., description="Application name")
    environment: str = Field(..., description="Active environment")
    database: str = Field(..., description="PostgreSQL connection status")
    redis: str = Field(..., description="Redis connection status")
    version: str = Field(default="1.0.0", description="Application version")
