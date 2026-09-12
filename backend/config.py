"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration; every value overridable via env vars.

    Security defaults are production-safe: DEV_AUTH must be explicitly
    enabled for local development, CORS origins are an explicit allowlist.
    """

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_db_url: str = ""
    validation_protocol_version: str = "sih26142_v1"
    worker_concurrency: int = 1
    max_tile_pixels: int = 4 * 1024 * 1024
    artifact_root: str = "./data/artifacts"
    # Dev mode: accept X-Dev-User header as identity when no JWT is present.
    # MUST stay false outside local development.
    dev_auth: bool = False
    # Comma-separated CORS origin allowlist (empty disables CORS middleware).
    cors_origins: str = ""
    # Provenance (PRD §14): immutable build identifiers.
    code_commit: str = ""
    worker_image: str = ""
    # Copernicus Data Space credentials (free CDSE account; download only).
    # Catalogue SEARCH stays anonymous — credentials never gate discovery.
    copernicus_username: str = ""
    copernicus_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def storage_url(self) -> str:
        """Supabase Storage REST base URL."""
        return f"{self.supabase_url.rstrip('/')}/storage/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS allowlist."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
