"""Artifact endpoints: authenticated reads and short-lived signed downloads.

Two read paths, both project-authorized:

``GET /{id}/content``
    Streams the artifact to an authenticated caller. This is the path the
    console uses for previews and JSON artifacts, so a locally-run deployment
    (artifacts on disk, no object storage) is fully usable without inventing a
    second data source.

``POST /{id}/signed-url``
    Returns a short-lived Supabase Storage URL for external hand-off. Requires
    object storage to be configured.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.config import get_settings
from backend.errors import ApiError, ARTIFACT_WRITE_FAILED, NOT_FOUND
from backend.schemas import SignedUrlOut

router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])

log = logging.getLogger("sentry.artifacts")

TTL = 3600


def _artifact_or_403(artifact_id: str, user: dict) -> dict:
    """Resolve an artifact and enforce project role access."""
    artifact = db.query(
        "select id, storage_bucket, object_key, media_type, job_id "
        "from raster_artifacts where id = %s",
        (artifact_id,), one=True,
    )
    if artifact is None:
        raise ApiError(NOT_FOUND, "artifact not found", 404)
    job = db.query("select project_id from jobs where id = %s",
                   (artifact["job_id"],), one=True)
    if job is None:
        raise ApiError(NOT_FOUND, "parent job not found", 404)
    require_project_role(user, job["project_id"],
                         ["owner", "operator", "reviewer", "viewer"])
    return artifact


@router.get("/{artifact_id}/content")
async def get_content(artifact_id: str,
                      user: dict = Depends(get_current_user)) -> Response:
    """Stream one artifact's bytes to an authenticated, authorized caller."""
    artifact = _artifact_or_403(artifact_id, user)
    settings = get_settings()
    media_type = artifact.get("media_type") or "application/octet-stream"

    storage_ready = bool(settings.supabase_url and settings.supabase_service_role_key)
    # Resolve inside artifact_root: object keys are worker-written, but a
    # compromised row must never turn this endpoint into a file reader.
    root = Path(settings.artifact_root).resolve()
    local = (root / artifact["storage_bucket"] / artifact["object_key"]).resolve()
    try:
        local.relative_to(root)
    except ValueError:
        raise ApiError(NOT_FOUND, "artifact not found", 404) from None
    if not storage_ready and local.is_file():
        # Local deployment: the worker wrote this file under artifact_root. Only
        # reachable through the same authorization check above.
        return FileResponse(local, media_type=media_type)

    if not storage_ready:
        raise ApiError(ARTIFACT_WRITE_FAILED,
                       "artifact is not available locally and object storage is "
                       "not configured", 503)
    object_url = (
        f"{settings.storage_url}/object/{quote(artifact['storage_bucket'], safe='')}/"
        f"{quote(artifact['object_key'], safe='/')}"
    )
    storage_headers = {
        "authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    # Status pre-check with a 1-byte range fetch (never buffered): the stream
    # below cannot change the HTTP status once bytes start flowing, so a
    # missing object must be rejected here with the stable error envelope.
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", object_url, headers={
                **storage_headers, "Range": "bytes=0-0",
            }) as probe:
                if probe.status_code not in (200, 206, 416):
                    raise ApiError(ARTIFACT_WRITE_FAILED,
                                   f"storage read failed ({probe.status_code})", 502)
    except ApiError:
        raise
    except httpx.HTTPError as exc:
        raise ApiError(ARTIFACT_WRITE_FAILED, "storage read failed", 502) from exc

    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=3600.0) as stream_client:
                async with stream_client.stream(
                    "GET", object_url, headers=storage_headers,
                ) as stream_resp:
                    if stream_resp.status_code != 200:
                        # The pre-check above passed, so this is a transient
                        # mid-flight failure: stop the body and log. Raising
                        # here aborts the stream instead of truncating silently.
                        log.warning("storage stream for %s/%s failed mid-flight: %s",
                                    artifact["storage_bucket"], artifact["object_key"],
                                    stream_resp.status_code)
                        raise ApiError(ARTIFACT_WRITE_FAILED,
                                       f"storage stream failed ({stream_resp.status_code})", 502)
                    async for chunk in stream_resp.aiter_bytes(1 << 20):
                        yield chunk
        except ApiError:
            raise
        except httpx.HTTPError as exc:
            raise ApiError(ARTIFACT_WRITE_FAILED, "storage stream failed", 502) from exc

    # Streamed, never buffered: COGs can be gigabytes and must not be held in
    # API-process RAM.
    return StreamingResponse(_stream(), media_type=media_type)


@router.post("/{artifact_id}/signed-url", response_model=SignedUrlOut)
async def signed_url(artifact_id: str,
                     user: dict = Depends(get_current_user)) -> SignedUrlOut:
    """Create a short-lived Storage signed URL for a project-scoped artifact."""
    artifact = _artifact_or_403(artifact_id, user)

    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        raise ApiError(ARTIFACT_WRITE_FAILED,
                       "object storage is not configured; use artifact content "
                       "for local deployments", 503)
    bucket, key = artifact["storage_bucket"], artifact["object_key"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.storage_url}/object/sign/"
            f"{quote(bucket, safe='')}/{quote(key, safe='/')}",
            json={"expiresIn": TTL},
            headers={
                "authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
        )
    try:
        data = resp.json()
    except Exception as exc:
        raise ApiError(ARTIFACT_WRITE_FAILED,
                       "storage sign returned a non-JSON response", 502) from exc
    if resp.status_code != 200 or not isinstance(data, dict) or "signedURL" not in data:
        raise ApiError(ARTIFACT_WRITE_FAILED, "storage sign request failed", 502)
    signed = data["signedURL"]
    base = settings.storage_url
    url = signed if signed.startswith("http") else f"{base}{signed}"
    return SignedUrlOut(url=url, expires_in=TTL)
