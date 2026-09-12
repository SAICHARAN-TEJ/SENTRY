"""Artifact endpoints: short-lived signed download URLs."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.config import get_settings
from backend.errors import ApiError, ARTIFACT_WRITE_FAILED
from backend.schemas import SignedUrlOut

router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])

TTL = 3600


@router.post("/{artifact_id}/signed-url", response_model=SignedUrlOut)
async def signed_url(artifact_id: str,
                     user: dict = Depends(get_current_user)) -> SignedUrlOut:
    """Create a short-lived Storage signed URL for a project-scoped artifact."""
    artifact = db.query(
        "select storage_bucket, object_key, job_id from raster_artifacts where id = %s",
        (artifact_id,), one=True,
    )
    if artifact is None:
        raise ApiError(ARTIFACT_WRITE_FAILED, "artifact not found", 404)
    job = db.query("select project_id from jobs where id = %s",
                   (artifact["job_id"],), one=True)
    if job is None:
        raise ApiError(ARTIFACT_WRITE_FAILED, "parent job not found", 404)
    require_project_role(user, job["project_id"],
                         ["owner", "operator", "reviewer", "viewer"])

    settings = get_settings()
    bucket, key = artifact["storage_bucket"], artifact["object_key"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.storage_url}/object/sign/{bucket}/{key}",
            json={"expiresIn": TTL},
            headers={
                "authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
        )
    if resp.status_code != 200 or "signedURL" not in resp.json():
        raise ApiError(ARTIFACT_WRITE_FAILED, "storage sign request failed", 502)
    signed = resp.json()["signedURL"]
    base = settings.storage_url
    url = signed if signed.startswith("http") else f"{base}{signed}"
    return SignedUrlOut(url=url, expires_in=TTL)
