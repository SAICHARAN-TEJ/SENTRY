"""Small server-side Supabase Storage client.

The service-role credential is read only from the backend environment and is
never returned to callers.  Workers may use this module for immutable object
uploads; API handlers use it only for short-lived signed URLs.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from backend.config import get_settings
from backend.errors import ApiError, ARTIFACT_WRITE_FAILED


def _headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key
    if not key:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Supabase service key is not configured", 503)
    return {"apikey": key, "authorization": f"Bearer {key}"}


def upload_file(bucket: str, key: str, path: str | Path) -> None:
    """Upload an immutable object, treating an existing object as idempotent."""
    settings = get_settings()
    if not settings.supabase_url:
        return
    try:
        response = httpx.post(
            f"{settings.storage_url}/object/{bucket}/{key}",
            headers={**_headers(), "content-type": "application/octet-stream", "x-upsert": "true"},
            content=Path(path).read_bytes(),
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Supabase Storage is unreachable", 503) from exc
    if response.status_code not in (200, 201):
        raise ApiError(ARTIFACT_WRITE_FAILED,
                       f"Storage upload failed with HTTP {response.status_code}", 502)


def signed_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Return a short-lived signed URL for a private object."""
    settings = get_settings()
    if not settings.supabase_url:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Supabase Storage is not configured", 503)
    try:
        response = httpx.post(
            f"{settings.storage_url}/object/sign/{bucket}/{key}",
            headers={**_headers(), "content-type": "application/json"},
            json={"expiresIn": expires_in},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Supabase Storage is unreachable", 503) from exc
    if response.status_code >= 300:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Storage signing failed", 502)
    signed = response.json().get("signedURL")
    if not signed:
        raise ApiError(ARTIFACT_WRITE_FAILED, "Storage returned no signed URL", 502)
    return signed if signed.startswith("http") else f"{settings.storage_url}{signed}"
