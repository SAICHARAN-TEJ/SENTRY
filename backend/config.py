"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    # Where job artifacts go.
    #   auto    (default) object storage when configured; on-disk artifacts only
    #           for a deployment with NO database at all (offline pipeline / CI).
    #           A database-backed deployment with no Storage resolves to
    #           "misconfigured" and the worker refuses to register artifacts, so
    #           they can never silently become local-only.
    #   storage require Supabase Storage; fail closed without it
    #   local   explicit single-machine opt-in: Postgres for metadata + artifacts
    #           on disk, served by the API's authenticated content path. Every
    #           provenance record states this, so no report can imply that
    #           objects were uploaded to object storage when they were not.
    artifact_store: Literal["auto", "storage", "local"] = "auto"
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
    # Job lease / reaper: CLAIMED jobs hold a lease that must be renewed by a
    # worker heartbeat. A claim whose lease has lapsed is stale (worker died);
    # the reaper requeues it until JOB_MAX_ATTEMPTS, then fails it permanently.
    job_lease_seconds: int = 300
    job_max_attempts: int = 3
    # Real ESA OpenSR / LDSR-S2 model (worker/opensr.py). The default checkpoint
    # path + SHA-256 are pinned in SOURCES.md; loading fails closed on mismatch.
    #   opensr_checkpoint          override the checkpoint path (recorded as
    #                              unverified unless opensr_checkpoint_sha256 matches)
    #   opensr_device              "cuda" | "cpu" | "" (auto: CUDA when available)
    #   opensr_sampling_steps      DDIM denoising steps for SR (upstream default 100)
    #   uncertainty_samples        stochastic draws for the uncertainty map (>3)
    #   uncertainty_sampling_steps DDIM steps used inside each uncertainty draw
    #   opensr_window/overlap      LR tiling: 128 px native window, 4x -> 512 px SR
    opensr_checkpoint: str = ""
    opensr_checkpoint_sha256: str = ""
    opensr_device: str = ""
    opensr_sampling_steps: int = 100
    opensr_window: int = 128
    opensr_overlap: int = 16
    uncertainty_samples: int = 8
    uncertainty_sampling_steps: int = 100
    uncertainty_enabled: bool = True
    # Multi-frame fusion is experimental: frames whose spectral change-risk
    # exceeds this (mean SAM in radians vs the reference revisit) are excluded
    # from fusion instead of being blended in silently.
    frame_change_risk_max: float = 0.25
    frame_max_selected: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def storage_url(self) -> str:
        """Supabase Storage REST base URL (empty when unconfigured)."""
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url.rstrip('/')}/storage/v1"

    @property
    def storage_configured(self) -> bool:
        """True when object storage has both a base URL and a service key."""
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def artifact_store_mode(self) -> str:
        """Resolve ``artifact_store`` to 'storage', 'local' or 'misconfigured'.

        'misconfigured' is a deliberate dead end rather than a fallback: a
        database-backed deployment whose artifacts would land only on one
        machine's disk must fail loudly, because artifact rows would otherwise
        point at objects no other client can fetch.
        """
        if self.artifact_store == "local":
            return "local"
        if self.artifact_store == "storage":
            return "storage" if self.storage_configured else "misconfigured"
        if self.storage_configured:
            return "storage"
        if not self.supabase_db_url:
            # Offline pipeline / tests: no database, so nothing is published and
            # on-disk artifacts are the only coherent choice.
            return "local"
        return "misconfigured"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS allowlist."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
