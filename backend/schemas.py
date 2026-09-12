"""Pydantic request/response models matching the PRD API contracts (13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Projects ---------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    organization_id: str | None = None
    default_crs: str = "EPSG:4326"


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    organization_id: str | None
    default_crs: str
    created_at: datetime | None = None


# --- AOIs -------------------------------------------------------------------

class AoiCreate(BaseModel):
    project_id: str
    name: str
    geometry: dict[str, Any]
    source_crs: str = "EPSG:4326"


class AoiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    bbox: list[float] | None = None
    area_m2: float | None = None
    created_at: datetime | None = None


# --- Scenes -----------------------------------------------------------------

class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_product_id: str
    sensing_time: datetime | None = None
    cloud_pct: float | None = None
    crs: str | None = None
    resolution_m: float | None = None
    ingest_status: str


# --- Jobs -------------------------------------------------------------------

class JobCreate(BaseModel):
    project_id: str
    aoi_id: str | None = None
    scene_ids: list[str] = Field(default_factory=list)
    mode: str = "reconstruct_validate"
    model: str = "custom_mf_sr"
    validation_protocol: str | None = None
    reference_id: str | None = None
    config_id: str | None = None
    idempotency_key: str


class JobStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    progress: float = 0.0
    attempt: int = 0
    metrics: dict | None = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    artifact_type: str
    storage_bucket: str
    object_key: str
    checksum: str | None = None
    bytes: int | None = None
    media_type: str | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    job_type: str
    status: str
    progress: float
    steps: list[JobStepOut] = []
    artifacts: list[ArtifactOut] = []
    validation_id: str | None = None
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

    id: str
    overall_status: str | None
    score: float | None
    evaluation_grid_m: float
    metrics: list[ValidationMetricOut] = []
    uncertainty: dict | None = None
    protocol: str
    status: str
    queue_job_id: str | None = None


# --- Reports ----------------------------------------------------------------

class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    validation_run_id: str
    summary_json: dict | None = None
    report_object_key: str | None = None
    created_at: datetime | None = None


# --- Misc --------------------------------------------------------------------

class SignedUrlOut(BaseModel):
    url: str
    expires_in: int


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    framework: str | None = None
    model_card: dict | None = None


class HealthOut(BaseModel):
    status: str
    db: bool
    storage: bool
    protocol_version: str


class ErrorResponse(BaseModel):
    error: dict[str, str]
