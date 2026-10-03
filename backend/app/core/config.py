"""Application configuration management using Pydantic Settings."""

import json
from pathlib import Path
from typing import List, Union, Literal
from sqlalchemy.engine import make_url
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CartPilot application settings loaded from environment or .env."""

    APP_NAME: str = "CartPilot"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    REQUIRE_AUTH: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = Field(8000, ge=1, le=65535)
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    DATABASE_URL: str = Field(default="", repr=False)
    REDIS_URL: str = Field(default="redis://localhost:6379/0", repr=False)
    DATABASE_POOL_MODE: Literal["pooled", "null"] = "pooled"

    GEMINI_API_KEY: str = ""
    JWT_SECRET: str = "dev-secret-key-change-in-production"

    # Pricing Agent Settings (Phase 3)
    MAX_PRICE_INCREASE_PERCENT: float = Field(10.0, ge=0, allow_inf_nan=False)
    MAX_PRICE_DECREASE_PERCENT: float = Field(10.0, ge=0, lt=100, allow_inf_nan=False)
    PRICING_LOOKBACK_DAYS: int = Field(14, gt=0)
    MIN_MARGIN_PERCENT: float = Field(0.0, ge=0, allow_inf_nan=False)
    PRICING_ADJUSTMENT_PERCENT: float = Field(5.0, ge=0, lt=100, allow_inf_nan=False)

    # Restock Agent Settings (Phase 4)
    RESTOCK_LOOKBACK_DAYS: int = Field(14, gt=0)
    DEFAULT_LEAD_TIME_DAYS: float = Field(5.0, ge=0, allow_inf_nan=False)
    SAFETY_STOCK_DAYS: float = Field(2.0, ge=0, allow_inf_nan=False)
    MAX_REORDER_QUANTITY: int = Field(500, gt=0)

    # Promotion settings: retained gross margin, distinct from pricing's cost markup.
    PROMOTION_LOOKBACK_DAYS: int = Field(14, ge=2)
    MAX_PROMOTION_DISCOUNT_PERCENT: float = Field(20, ge=0, lt=100, allow_inf_nan=False)
    PROMOTION_MIN_MARGIN_PERCENT: float = Field(10, ge=0, lt=100, allow_inf_nan=False)
    HIGH_INVENTORY_DAYS_THRESHOLD: float = Field(45, gt=0, allow_inf_nan=False)
    SLOW_SALES_THRESHOLD: float = Field(1.5, ge=0, allow_inf_nan=False)
    PROMOTION_ZERO_SALES_MIN_INVENTORY: int = Field(30, gt=0)
    PROMOTION_TREND_CHANGE_PERCENT: float = Field(20, ge=0, lt=100, allow_inf_nan=False)
    PROMOTION_MILD_DISCOUNT_PERCENT: float = Field(5, ge=0, lt=100, allow_inf_nan=False)
    PROMOTION_MODERATE_DISCOUNT_PERCENT: float = Field(10, ge=0, lt=100, allow_inf_nan=False)
    PROMOTION_SEVERE_DISCOUNT_PERCENT: float = Field(15, ge=0, lt=100, allow_inf_nan=False)

    SHOPIFY_STORE_DOMAIN: str = ""
    SHOPIFY_ACCESS_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False)
    SHOPIFY_API_VERSION: str = Field("2026-10", pattern=r"^20\d{2}-(01|04|07|10)$")
    SHOPIFY_MERCHANT_ID: int | None = Field(default=None, gt=0)
    SHOPIFY_TIMEOUT_SECONDS: float = Field(30, gt=0, le=60, allow_inf_nan=False)
    SHOPIFY_MAX_RETRIES: int = Field(3, ge=0, le=5)
    SHOPIFY_MAX_PAGES: int = Field(100, ge=1, le=1000)
    SHOPIFY_READ_COSTS: bool = True

    @field_validator("SHOPIFY_MERCHANT_ID", mode="before")
    @classmethod
    def optional_merchant_id(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("SHOPIFY_STORE_DOMAIN")
    @classmethod
    def valid_shop_domain(cls, value: str) -> str:
        import re
        value = value.strip().lower()
        if value and not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com", value):
            raise ValueError("Use a bare store-name.myshopify.com domain.")
        return value

    MAX_ACTIONS_PER_PLAN: int = Field(5, ge=1, le=100)

    # Listing quality checks and output bounds (Phase 8).
    MIN_TITLE_LENGTH: int = Field(10, gt=0, le=255)
    MAX_TITLE_LENGTH: int = Field(120, gt=0, le=255)
    MIN_DESCRIPTION_LENGTH: int = Field(80, gt=0)
    MAX_DESCRIPTION_LENGTH: int = Field(2000, gt=0)
    LISTING_POOR_QUALITY_THRESHOLD: float = Field(.6, ge=0, le=1, allow_inf_nan=False)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins whether provided as a JSON list, comma-separated string, or list."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_local_environment(self) -> bool:
        """Only trusted local/test environments enable the existing guarded routes."""
        return self.ENVIRONMENT in ("development", "test")

    @model_validator(mode="after")
    def deployment_settings(self) -> "Settings":
        if not self.DATABASE_URL.strip():
            if self.ENVIRONMENT == "production":
                raise ValueError("Production requires an explicit DATABASE_URL.")
            self.DATABASE_URL = "postgresql+asyncpg://cartpilot:cartpilot@localhost:5432/cartpilot"
        try:
            url = make_url(self.DATABASE_URL.strip())
            if url.drivername in ("postgres", "postgresql"):
                url = url.set(drivername="postgresql+asyncpg")
            if url.drivername not in ("postgresql+asyncpg", "sqlite+aiosqlite"):
                raise ValueError("Unsupported async database driver")
            if url.drivername == "postgresql+asyncpg":
                if not url.host or not url.database:
                    raise ValueError("Missing PostgreSQL host/database")
                query = dict(url.query)
                if "sslmode" in query:
                    if "ssl" in query:
                        raise ValueError("Conflicting TLS options")
                    query["ssl"] = query.pop("sslmode")
                url = url.set(query=query)
            self.DATABASE_URL = url.render_as_string(hide_password=False)
        except Exception:
            raise ValueError("DATABASE_URL must be a valid async PostgreSQL or SQLite URL.") from None
        if self.ENVIRONMENT == "production" and self.LOG_LEVEL == "DEBUG":
            raise ValueError("Production LOG_LEVEL must not be DEBUG.")
        return self

    @model_validator(mode="after")
    def production_cors(self) -> "Settings":
        if self.ENVIRONMENT == "production" and any("*" in origin for origin in self.CORS_ORIGINS):
            raise ValueError("Production CORS requires explicit frontend origins.")
        return self

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[3] / ".env", Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()
