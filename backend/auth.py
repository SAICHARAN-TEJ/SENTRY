"""Request authentication + project-role authorization (defense in depth; RLS is the real gate)."""

from __future__ import annotations

import httpx
from fastapi import Request

from backend import db
from backend.config import get_settings
from backend.errors import ApiError, AUTH_FORBIDDEN

ALL_ROLES = ["owner", "operator", "reviewer", "viewer"]


async def get_current_user(request: Request) -> dict:
    """Resolve the calling user from a Supabase JWT or the dev header."""
    settings = get_settings()
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        if not settings.supabase_url or not settings.supabase_anon_key:
            # Never substitute the service-role key for end-user token
            # verification: that would hide a production misconfiguration and
            # unnecessarily expose a privileged credential to Auth.
            raise ApiError(AUTH_FORBIDDEN, "Supabase user authentication is not configured", 500)
        token = auth_header[7:].strip()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "authorization": f"Bearer {token}",
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            return {"id": data.get("id"), "email": data.get("email")}
        raise ApiError(AUTH_FORBIDDEN, "invalid or expired token", 401)

    dev_user = request.headers.get("x-dev-user", "").strip()
    if settings.dev_auth and dev_user:
        return {"id": dev_user, "email": None}

    raise ApiError(AUTH_FORBIDDEN, "authentication required", 401)


def require_project_role(user: dict, project_id: str, roles: list[str]) -> str:
    """Return the user's role on the project or raise AUTH_FORBIDDEN.

    Note: Postgres RLS is the authoritative enforcement layer; this check gives
    the FastAPI service connection (which bypasses RLS) equivalent semantics.
    """
    row = db.query(
        "select role from project_members where project_id = %s and user_id = %s",
        (project_id, user["id"]),
        one=True,
    )
    if row is None or not isinstance(row, dict):
        raise ApiError(AUTH_FORBIDDEN, "forbidden for this project")
    role = row.get("role", "")
    if role not in roles:
        raise ApiError(AUTH_FORBIDDEN, "forbidden for this project")
    return role
