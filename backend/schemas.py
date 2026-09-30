"""Pydantic request/response models matching the PRD API contracts (13)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_uuid(value: Any) -> Any:
    """Accept psycopg UUID objects for id fields; the wire format stays str."""
    return str(value) if isinstance(value, UUID) else value


UuidStr = Annotated[str, BeforeValidator(_coerce_uuid)]


# --- Projects ---------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    organization_id: UuidStr | None = None
    default_crs: str = "EPSG:4326"


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    name: str
    organization_id: UuidStr | None
    default_crs: str
    created_at: datetime | None = None


# --- AOIs -------------------------------------------------------------------

class AoiCreate(BaseModel):
    project_id: UuidStr
    name: str
    geometry: dict[str, Any]
    source_crs: str = "EPSG:4326"


class AoiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    project_id: UuidStr
    name: str
    bbox: list[float] | None = None
    area_m2: float | None = None
    created_at: datetime | None = None


# --- Scenes -----------------------------------------------------------------

class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    provider_product_id: str
    sensing_time: datetime | None = None
    cloud_pct: float | None = None
    crs: str | None = None
    resolution_m: float | None = None
    ingest_status: str


# --- Jobs -------------------------------------------------------------------

class JobCreate(BaseModel):
    project_id: UuidStr
    aoi_id: str | None = None
    scene_ids: list[str] = Field(default_factory=list)
    mode: str = "reconstruct_validate"
    model: str = "bicubic_4x"
    validation_protocol: str | None = None
    reference_id: str | None = None
    config_id: str | None = None
    idempotency_key: str
    # Advanced knobs (per-job overrides; None = server default from settings).
    # Stored in job_inputs role='advanced_knobs' so no migration is needed.
    sampling_steps: int | None = Field(default=None, ge=1, le=1000)
    uncertainty_samples: int | None = Field(default=None, ge=1, le=64)
    uncertainty_enabled: bool | None = None
    frame_max_selected: int | None = Field(default=None, ge=1, le=8)
    frame_change_risk_max: float | None = Field(default=None, ge=0.0, le=3.2)


class JobStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    progress: float = 0.0
    attempt: int = 0
    metrics: dict | None = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    artifact_type: str
    storage_bucket: str
    object_key: str
    checksum: str | None = None
    bytes: int | None = None
    media_type: str | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    project_id: UuidStr
    job_type: str
    status: str
    progress: float
    steps: list[JobStepOut] = []
    artifacts: list[ArtifactOut] = []
    validation_id: UuidStr | None = None
    error: dict | None = None


# --- Validation -------------------------------------------------------------

class ValidationMetricOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    band: str | None = None
    value: float | None = None
    threshold: float | None = None
    pass_: bool | None = Field(None, alias="pass")


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    overall_status: str | None
    score: float | None
    evaluation_grid_m: float
    metrics: list[ValidationMetricOut] = []
    uncertainty: dict | None = None
    protocol: str
    status: str
    queue_job_id: UuidStr | None = None


# --- Reports ----------------------------------------------------------------

class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    validation_run_id: UuidStr
    summary_json: dict | None = None
    report_object_key: str | None = None
    created_at: datetime | None = None


# --- Misc --------------------------------------------------------------------

class SignedUrlOut(BaseModel):
    url: str
    expires_in: int


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    name: str
    version: str
    framework: str | None = None
    model_card: dict | None = None


class HealthOut(BaseModel):
    status: str
    db: bool
    storage: bool
    # Resolved artifact backend: 'storage' (object storage), 'local' (artifacts
    # on this machine's disk) or 'misconfigured' (neither available; the worker
    # will refuse to register artifacts rather than downgrade silently).
    artifacts: str
    protocol_version: str
    # True when the backend accepts X-Dev-User identities (local dev). The
    # console uses this to decide whether the one-click dev session is
    # available; production deployments keep it false and the console keeps
    # asking for a JWT.
    dev_auth: bool = False


class DevSessionOut(BaseModel):
    """One-call local-dev operator session (see backend/routers/dev_session.py)."""
    user_id: str
    dev_auth: bool
    project: dict
    aoi: dict | None = None
    # id, provider_product_id, sensing_time, cloud_pct of the newest staged
    # scene whose band files actually exist on disk; null when none is staged.
    scene: dict | None = None


class ErrorResponse(BaseModel):
    error: dict[str, str]
