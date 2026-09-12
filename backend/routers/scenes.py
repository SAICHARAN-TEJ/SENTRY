"""Scene search: resolve Sentinel-2 scenes intersecting an AOI."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.errors import ApiError, SCENE_NOT_FOUND
from backend.schemas import SceneOut

router = APIRouter(prefix="/v1/scenes", tags=["scenes"])


@router.get("/search", response_model=list[SceneOut])
async def search_scenes(
    project_id: str,
    aoi_id: str,
    start: str | None = None,
    end: str | None = None,
    max_cloud: float | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> list[SceneOut]:
    """Return scenes whose footprint intersects the AOI (geometry validated by PostGIS)."""
    require_project_role(user, project_id, ["owner", "operator", "reviewer", "viewer"])

    aoi = db.query(
        "select id, project_id from aois where id = %s and project_id = %s",
        (aoi_id, project_id),
        one=True,
    )
    if aoi is None:
        raise ApiError(SCENE_NOT_FOUND, "AOI not found")

    clauses = [
        "s.footprint is not null",
        "ST_Intersects(s.footprint, (select geom from aois where id = %s))",
    ]
    params: list = [aoi_id]
    if start:
        clauses.append("s.sensing_time >= %s")
        params.append(start)
    if end:
        clauses.append("s.sensing_time <= %s")
        params.append(end)
    if max_cloud is not None:
        clauses.append("(s.cloud_pct is null or s.cloud_pct <= %s)")
        params.append(max_cloud)
    params.append(min(limit, 500))

    rows = db.query(
        f"""
        select s.id, s.provider_product_id, s.sensing_time, s.cloud_pct,
               s.crs, s.resolution_m, s.ingest_status
        from scenes s
        where {' and '.join(clauses)}
        order by s.sensing_time desc nulls last
        limit %s
        """,
        tuple(params),
    )
    return [SceneOut(**r) for r in rows]  # type: ignore[misc]
