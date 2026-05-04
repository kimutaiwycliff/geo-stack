"""Application configuration loaded from environment variables via pydantic-settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime environment
    env: str = Field(default="local", pattern="^(local|cloud|production)$")
    log_level: str = Field(default="info", pattern="^(debug|info|warning|error)$")
    show_docs: bool = True

    # Database
    database_url: str
    db_pool_size: int = Field(default=5, ge=1, le=50)

    # API behaviour
    cors_origins: str = "http://localhost:5173"
    api_rate_limit: int = Field(default=100, ge=1)

    # Upstream services (internal Docker network URLs)
    martin_url: str = "http://martin:3000"
    titiler_url: str = "http://titiler:8080"

    # Data directory (mounted volume)
    data_dir: str = "/data"

    # Cloudflare R2 / S3 compatible object storage
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket_name: str = "geo-data"   # legacy — kept for backwards compat
    r2_pmtiles_bucket: str = "geo-pmtiles"
    r2_parquet_bucket: str = "geo-parquet"
    r2_uploads_bucket: str = "geo-uploads"
    r2_public_url: str = ""

    # Direct Supabase connection (port 5432) for ogr2ogr bulk-load.
    # The main DATABASE_URL uses the pooler (port 6543) which doesn't support COPY.
    supabase_direct_url: str = ""

    # DuckDB tuning
    duckdb_threads: int = Field(default=4, ge=1)
    duckdb_memory: str = "512MB"

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v  # kept as string; split in app startup

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.show_docs else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.show_docs else None


settings = Settings()  # type: ignore[call-arg]
