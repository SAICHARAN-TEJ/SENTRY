"""Local-development session bootstrap: one call, a working operator session.

Connecting the console used to require copying a backend URL, a user UUID and a
project UUID out of scripts or database dumps. This endpoint collapses that into
a single request for local demos: it returns a stable dev identity plus a ready
demo project and — when a staged Sentinel-2 scene exists — a central AOI over
that scene, so the console can list and run a job without anything being pasted.

Why it is safe to expose
------------------------
- Registered only when ``settings.dev_auth`` is true (see ``backend/main.py``);
  with ``DEV_AUTH=false`` the route does not exist at all — not 401, not 403,
  simply absent, so a production deployment has no surface to misconfigure.
- It is unauthenticated *on purpose*: its whole job is to mint the identity a
  fresh browser does not have yet. It can only ever return the fixed dev
  principal and data that principal itself created, so nothing project-scoped
  becomes reachable that the dev header would not already grant. Production
  auth (JWT) is unaffected: ``get_current_user`` never consults this route.
- ``GET /v1/models`` is already unauthenticated by design (see
  ``backend/routers/models.py``): capability facts stay public, data does not.
  This endpoint follows the same line — it grants a *principal*, not access to
  anyone's data.
- Idempotent by construction: the demo project and AOI are matched by fixed
  names before any insert, so repeated connects never duplicate rows.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from psycopg.types.json import Json
from pyproj import Geod
from shapely import wkt as shapely_wkt
from shapely.geometry import box
from shapely.geometry.multipolygon import MultiPolygon

from backend import db
from backend.config import get_settings
from backend.schemas import DevSessionOut

router = APIRouter(prefix="/v1/dev", tags=["dev"])

# Stable, obviously-synthetic dev identity so repeated connects reuse the same
# rows instead of minting a new project on every click. Same principal the
# judge demo uses, so demo data stays in one place.
DEV_USER = "00000000-0000-4000-8000-0000000000d0"
DEMO_PROJECT_NAME = "SUBPIXEL-SENTRY demo"
DEMO_AOI_NAME = "demo AOI (central 50%)"
# Central half-extent fraction, identical to the judge demo's AOI.
AOI_INSET = 0.25


def _staged_scene() -> dict | None:
    """Newest ready scene whose four staged band files all exist on disk.

    Same rule as ``scripts/judge_demo.py::find_staged_scene``: a scene row
    without its files would make the console offer a run that fails later.
    """
    root = Path(get_settings().artifact_root)
    rows = db.query(
        """
        select id, provider_product_id, crs, resolution_m, cloud_pct, sensing_time,
               ST_AsText(footprint) as footprint
          from scenes
         where ingest_status = 'ready' and footprint is not null
         order by created_at desc
        """
    ) or []
    for row in rows:
        bands = db.query(
            "select band_name, object_key from scene_bands where scene_id = %s",
            (row["id"],),
        ) or []
        if len(bands) != 4:
            continue
        if all((root / b["object_key"]).exists()
               or (root / "scene-assets" / b["object_key"]).exists()
               for b in bands):
            return row
    return None


def _ensure_demo_aoi(project_id: str, footprint_wkt: str) -> dict | None:
    """Create (once) a central AOI over the staged scene's footprint."""
    have = db.query(
        "select id, project_id, name, bbox, area_m2, created_at from aois "
        "where project_id = %s and name = %s limit 1",
        (project_id, DEMO_AOI_NAME), one=True)
    if have is not None:
        return have

    poly = shapely_wkt.loads(footprint_wkt)
    minx, miny, maxx, maxy = poly.bounds
    dx, dy = (maxx - minx) * AOI_INSET, (maxy - miny) * AOI_INSET
    geom = MultiPolygon([box(minx + dx, miny + dy, maxx - dx, maxy - dy)])
    # Same bbox/area computation contract as POST /v1/aois.
    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.geometry_area_perimeter(geom)
    bbox = [geom.bounds[0], geom.bounds[1], geom.bounds[2], geom.bounds[3]]
    row = db.query(
        """
        insert into aois (project_id, name, geom, bbox, area_m2)
        values (%s, %s, ST_Multi(ST_GeomFromText(%s, 4326)), %s, %s)
        returning id, project_id, name, bbox, area_m2, created_at
        """,
        (project_id, DEMO_AOI_NAME, geom.wkt, Json(bbox), abs(area_m2)),
        one=True,
    )
    return row


@router.post("/session", response_model=DevSessionOut)
async def create_dev_session() -> DevSessionOut:
    """Return a ready-to-use dev scope: identity, demo project, AOI, scene.

    No identity is required to call this — minting one is the point. The demo
    project is created once and reused, and every element it returns belongs to
    the fixed dev principal above.
    """
    project = db.query(
        """
        select p.id, p.name, p.organization_id, p.default_crs, p.created_at
        from projects p
        join project_members pm on pm.project_id = p.id
        where pm.user_id = %s and p.name = %s
        order by p.created_at desc
        limit 1
        """,
        (DEV_USER, DEMO_PROJECT_NAME),
        one=True,
    )
    if project is None:
        with db.transaction() as tx:
            org = tx.query(
                "insert into organizations (name, created_by) values (%s, %s) returning id",
                (f"demo {DEV_USER[:8]}", DEV_USER), one=True)
            project = tx.query(
                """
                insert into projects (organization_id, name, default_crs)
                values (%s, %s, 'EPSG:4326')
                returning id, name, organization_id, default_crs, created_at
                """,
                (org["id"], DEMO_PROJECT_NAME), one=True)
            tx.execute(
                "insert into project_members (project_id, user_id, role) "
                "values (%s, %s, 'owner') on conflict do nothing",
                (project["id"], DEV_USER))

    scene = _staged_scene()

    aoi = None
    if scene is not None:
        aoi = _ensure_demo_aoi(project["id"], scene["footprint"])

    return DevSessionOut(
        user_id=DEV_USER,
        dev_auth=True,
        project=project,
        aoi=aoi,
        scene=({k: scene[k] for k in
                ("id", "provider_product_id", "sensing_time", "cloud_pct")}
               if scene else None),
    )
