"""AOI endpoints: register GeoJSON multipolygons with CRS normalization."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pyproj import Geod, Transformer
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.errors import ApiError, INVALID_AOI
from backend.schemas import AoiCreate, AoiOut

router = APIRouter(prefix="/v1/aois", tags=["aois"])


@router.post("", status_code=201, response_model=AoiOut)
async def create_aoi(body: AoiCreate, user: dict = Depends(get_current_user)) -> AoiOut:
    """Validate + reproject an AOI to EPSG:4326 and persist with bbox/area."""
    require_project_role(user, body.project_id, ["owner", "operator"])

    try:
        geom = shape(body.geometry)
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(INVALID_AOI, f"malformed GeoJSON geometry: {exc}") from exc
    if geom.is_empty:
        raise ApiError(INVALID_AOI, "geometry is empty")

    if body.source_crs and body.source_crs.upper() != "EPSG:4326":
        try:
            transformer = Transformer.from_crs(body.source_crs, "EPSG:4326", always_xy=True)
            from shapely.ops import transform as shp_transform

            geom = shp_transform(transformer.transform, geom)
        except Exception as exc:  # noqa: BLE001 - projection failures are user input errors
            raise ApiError(INVALID_AOI, f"cannot reproject from {body.source_crs}: {exc}") from exc

    if not geom.is_valid:
        # PRD 13.1: INVALID_AOI for invalid geometry — no silent auto-repair,
        # because "fixed" geometry may not match the user's intent.
        raise ApiError(INVALID_AOI, "geometry invalid (self-intersection or degenerate); "
                                    "submit a valid MultiPolygon")

    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    if not isinstance(geom, MultiPolygon):
        raise ApiError(INVALID_AOI, "geometry must be a (multi)polygon")

    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.geometry_area_perimeter(geom)
    bbox = [geom.bounds[0], geom.bounds[1], geom.bounds[2], geom.bounds[3]]

    row = db.query(
        """
        insert into aois (project_id, name, geom, bbox, area_m2)
        values (%s, %s, ST_Multi(ST_GeomFromText(%s, 4326)), %s, %s)
        returning id, project_id, name, bbox, area_m2, created_at
        """,
        (body.project_id, body.name, geom.wkt,
         json.dumps(bbox), abs(area_m2)),
        one=True,
    )
    return AoiOut(**row)  # type: ignore[arg-type]


@router.get("", response_model=list[AoiOut])
async def list_aois(project_id: str, user: dict = Depends(get_current_user)) -> list[AoiOut]:
    """List AOIs of a project the user can read."""
    require_project_role(user, project_id, ["owner", "operator", "reviewer", "viewer"])
    rows = db.query(
        """
        select id, project_id, name, bbox, area_m2, created_at
        from aois where project_id = %s order by created_at desc
        """,
        (project_id,),
    )
    return [AoiOut(**r) for r in rows]  # type: ignore[misc]
