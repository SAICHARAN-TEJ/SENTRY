"""Copernicus endpoints: catalogue search + scene ingestion (PRD Table 3, Layer 1).

Search is read-only and available to any project role. Ingestion writes
scenes/scene_bands rows and stages band rasters, so it is restricted to
owner/operator — the same rule as AOI and job creation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend import copernicus
from backend.auth import get_current_user, require_project_role
from backend.routers.aois import _load_aoi_polygon_wkt

router = APIRouter(prefix="/v1/copernicus", tags=["copernicus"])


class CatalogSearchOut(BaseModel):
    product_id: str
    name: str
    tile_id: str
    satellite: str
    sensing_time: str
    online: bool
    footprint_wkt: str | None


class SearchRequest(BaseModel):
    project_id: str
    aoi_id: str
    start: str
    end: str
    max_cloud: float | None = Field(default=None, ge=0.0, le=100.0)
    top: int = Field(default=20, ge=1, le=100)


class IngestRequest(BaseModel):
    project_id: str
    aoi_id: str
    start: str
    end: str
    max_cloud: float | None = Field(default=None, ge=0.0, le=100.0)
    top: int = Field(default=3, ge=1, le=20)
    download: bool = True


@router.post("/search", response_model=list[CatalogSearchOut])
async def search_catalog(body: SearchRequest,
                         user: dict = Depends(get_current_user)) -> list[CatalogSearchOut]:
    """Query Sentinel-2 L2A products intersecting a registered AOI."""
    require_project_role(user, body.project_id,
                         ["owner", "operator", "reviewer", "viewer"])
    aoi_wkt = _load_aoi_polygon_wkt(body.project_id, body.aoi_id)
    products = copernicus.search_products(
        aoi_wkt, body.start, body.end,
        max_cloud=body.max_cloud, top=body.top)
    return [
        CatalogSearchOut(
            product_id=p.product_id, name=p.name, tile_id=p.tile_id,
            satellite=p.satellite, sensing_time=p.sensing_time.isoformat(),
            online=p.online, footprint_wkt=p.footprint_wkt,
        )
        for p in products
    ]


@router.post("/ingest")
async def ingest_catalog(body: IngestRequest,
                         user: dict = Depends(get_current_user)) -> dict:
    """Search + (optionally) download + stage scenes; idempotent per product."""
    require_project_role(user, body.project_id, ["owner", "operator"])
    aoi_wkt = _load_aoi_polygon_wkt(body.project_id, body.aoi_id)
    results = copernicus.search_and_ingest(
        aoi_wkt, body.start, body.end,
        max_cloud=body.max_cloud, top=body.top, download=body.download)
    return {"results": results}
