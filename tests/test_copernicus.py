"""Copernicus connector tests: parsing, band extraction, API surface.

Network-dependent paths (live catalogue, product download) are exercised through
monkeypatched HTTP so the suite stays offline-deterministic; the filter string
construction itself is asserted against the exact OData shape verified against
the live catalogue on 2026-09-12.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import copernicus
from backend.errors import ApiError
from backend.main import app

DEV = {"X-Dev-User": "00000000-0000-4000-8000-00000000aa01"}

PRODUCT_NAME = "S2A_MSIL2A_20260807T100701_N0512_R022_T33TTG_20260807T183309.SAFE"
ODATA_ROW = {
    "Id": "4c0a7f39-16ad-45a5-ba82-d2f4dfdf86d9",
    "Name": PRODUCT_NAME,
    "Online": True,
    "GeoFootprint": {
        "type": "Polygon",
        "coordinates": [[[12.0, 41.0], [13.0, 41.0], [13.0, 42.0],
                         [12.0, 42.0], [12.0, 41.0]]],
    },
}


def _make_safe_zip(bands=("02", "03", "04", "08")) -> bytes:
    """Synthetic SAFE zip with the 10m band layout the extractor expects."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("S2A_MSIL2A_20260807T100701_N0512_R022_T33TTG_20260807T183309.SAFE/"
                    "manifest.xml", "<product/>")
        for band in bands:
            zf.writestr(
                "S2A_MSIL2A_20260807T100701_N0512_R022_T33TTG_20260807T183309.SAFE/"
                f"GRANULE/L2A_T33TTG_A001234_20260807T100657/IMG_DATA/R10m/"
                f"T33TTG_20260807T100701_B{band}.jp2",
                f"JP2_BYTES_{band}",
            )
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def test_product_name_parse():
    p = copernicus.CatalogProduct.from_odata(ODATA_ROW)
    assert p.product_id == "4c0a7f39-16ad-45a5-ba82-d2f4dfdf86d9"
    assert p.tile_id == "33TTG"
    assert p.satellite == "S2A"
    assert p.baseline_version == "s2-processing-baseline-N0512"
    assert p.sensing_time.strftime("%Y%m%dT%H%M%S") == "20260807T100701"


def test_footprint_to_wkt():
    p = copernicus.CatalogProduct.from_odata(ODATA_ROW)
    assert p.footprint_wkt is not None
    assert p.footprint_wkt.startswith("POLYGON((12.0 41.0")
    assert p.footprint_wkt.endswith("12.0 41.0))")


def test_unrecognized_product_name_raises():
    with pytest.raises(ApiError) as ei:
        copernicus.CatalogProduct.from_odata({"Id": "x", "Name": "S3_FOO.SAFE"})
    assert ei.value.code == "DATA_CORRUPT"


# --------------------------------------------------------------------------- #
# Filter construction (shape verified against live catalogue)
# --------------------------------------------------------------------------- #

def test_search_filter_shape(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"value": []}

    def fake_get(url, params=None, timeout=None):
        captured["url"], captured["params"] = url, params
        return FakeResp()

    monkeypatch.setattr(copernicus.httpx, "get", fake_get)
    copernicus.search_products(
        "POLYGON((12.3 41.8,12.6 41.8,12.6 42.0,12.3 42.0,12.3 41.8))",
        "2026-08-01T00:00:00.000Z", "2026-09-01T00:00:00.000Z",
        max_cloud=20.0, top=5)

    f = captured["params"]["$filter"]
    assert "Collection/Name eq 'SENTINEL-2'" in f
    assert "contains(Name,'MSIL2A')" in f
    assert "OData.CSC.Intersects(area=geography'SRID=4326;POLYGON" in f
    assert "ContentDate/Start gt 2026-08-01T00:00:00.000Z" in f
    assert "Attributes/any(a: a/Name eq 'CloudCover'" in f
    assert "Value le 20.0)" in f
    assert captured["params"]["$top"] == 5


def test_search_rejects_non_polygon():
    with pytest.raises(ApiError) as ei:
        copernicus.search_products("POINT(12 41)", "2026-08-01T00:00:00Z",
                                   "2026-09-01T00:00:00Z")
    assert ei.value.code == "INVALID_AOI"


# --------------------------------------------------------------------------- #
# Band extraction + staging
# --------------------------------------------------------------------------- #

def test_extract_bands_roundtrip(tmp_path):
    zip_path = tmp_path / "product.zip"
    zip_path.write_bytes(_make_safe_zip())
    bands = copernicus.extract_bands(str(zip_path))
    assert set(bands) == {"B02", "B03", "B04", "B08"}
    assert bands["B02"] == b"JP2_BYTES_02"


def test_extract_bands_missing_band_fails(tmp_path):
    zip_path = tmp_path / "product.zip"
    zip_path.write_bytes(_make_safe_zip(bands=("02", "03", "04")))  # B08 absent
    with pytest.raises(ApiError) as ei:
        copernicus.extract_bands(str(zip_path))
    assert ei.value.code == "DATA_CORRUPT"
    assert "B08" in ei.value.message


def test_ingest_product_registers_scene_and_bands(tmp_path, monkeypatch, fake_db):
    # fake_db backs backend.db during ingest.register_scene.
    import rasterio

    class FakeRaster:
        def __init__(self):
            self.width, self.height = 1098, 1098
            self.transform = rasterio.transform.Affine(
                10.0, 0.0, 600000.0, 0.0, -10.0, 4900000.0)
            self.res = (10.0, 10.0)
            self.crs = type("CRS", (), {"to_string": lambda self: "EPSG:32633"})()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    calls = {"n": 0}

    def fake_open(*args, **kwargs):
        calls["n"] += 1
        return FakeRaster()

    monkeypatch.setattr(rasterio, "open", fake_open)
    monkeypatch.setattr("backend.copernicus.get_settings",
                        lambda: type("S", (), {"artifact_root": str(tmp_path)})())

    product = copernicus.CatalogProduct.from_odata(ODATA_ROW)
    zip_path = tmp_path / "p.zip"
    zip_path.write_bytes(_make_safe_zip())

    result = copernicus.ingest_product(product, str(zip_path))

    assert result["scene_id"] in fake_db.scenes
    assert result["tile_id"] == "33TTG"
    assert set(result["band_object_keys"]) == {"B02", "B03", "B04", "B08"}
    staged_bands = [b for b in fake_db.scene_bands
                    if b["scene_id"] == result["scene_id"]]
    assert len(staged_bands) == 4
    for b in staged_bands:  # band files actually written under artifact root
        assert (tmp_path / "scene-assets" / b["object_key"]).exists()
    assert calls["n"] >= 4  # grid cross-check opened every band


# --------------------------------------------------------------------------- #
# Download fail-closed behavior
# --------------------------------------------------------------------------- #

def test_download_requires_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.copernicus.get_settings", lambda: type(
        "S", (), {"copernicus_username": "", "copernicus_password": "",
                  "artifact_root": str(tmp_path)})())
    with pytest.raises(ApiError) as ei:
        copernicus.download_product("some-id", dest_dir=str(tmp_path))
    assert "CDSE account" in ei.value.message
    assert ei.value.code == "DATA_CORRUPT"


def test_download_resumes_existing_file(monkeypatch, tmp_path):
    existing = tmp_path / "scene-assets" / "copernicus" / "abc.zip"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already-here")
    monkeypatch.setattr("backend.copernicus.get_settings", lambda: type(
        "S", (), {"copernicus_username": "", "copernicus_password": "",
                  "artifact_root": str(tmp_path)})())
    # Must NOT raise despite missing credentials: file already present.
    assert copernicus.download_product("abc", dest_dir=str(tmp_path)) == str(existing)


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(fake_db):
    return TestClient(app)


def test_copernicus_search_endpoint(client, fake_db, monkeypatch):
    pid = client.post("/v1/projects", json={"name": "P"}, headers=DEV).json()["id"]
    aoi_id = fake_db.add_aoi(pid)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"value": [ODATA_ROW]}

    monkeypatch.setattr(
        copernicus.httpx, "get",
        lambda url, params=None, timeout=None: FakeResp())

    resp = client.post("/v1/copernicus/search", headers=DEV, json={
        "project_id": pid, "aoi_id": aoi_id,
        "start": "2026-08-01T00:00:00.000Z", "end": "2026-09-01T00:00:00.000Z",
        "max_cloud": 30, "top": 10,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == PRODUCT_NAME
    assert body[0]["tile_id"] == "33TTG"


def test_copernicus_ingest_requires_operator(client, fake_db, monkeypatch):
    pid = client.post("/v1/projects", json={"name": "P"}, headers=DEV).json()["id"]
    aoi_id = fake_db.add_aoi(pid)
    # A viewer must be rejected before any network call happens.
    fake_db.add_member(pid, "viewer-user", "viewer")
    resp = client.post("/v1/copernicus/ingest", headers={
        **DEV, "X-Dev-User": "viewer-user"}, json={
        "project_id": pid, "aoi_id": aoi_id,
        "start": "2026-08-01T00:00:00.000Z", "end": "2026-09-01T00:00:00.000Z",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_FORBIDDEN"


def test_copernicus_ingest_unknown_aoi(client, fake_db):
    pid = client.post("/v1/projects", json={"name": "P"}, headers=DEV).json()["id"]
    resp = client.post("/v1/copernicus/ingest", headers=DEV, json={
        "project_id": pid, "aoi_id": "00000000-0000-4000-8000-ffffffffffff",
        "start": "2026-08-01T00:00:00.000Z", "end": "2026-09-01T00:00:00.000Z",
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_copernicus_ingest_idempotent_flow(client, fake_db, monkeypatch, tmp_path):
    """Catalog-only mode registers nothing; a second ingest skips known products."""
    pid = client.post("/v1/projects", json={"name": "P"}, headers=DEV).json()["id"]
    aoi_id = fake_db.add_aoi(pid)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"value": [ODATA_ROW]}

    monkeypatch.setattr(
        copernicus.httpx, "get",
        lambda url, params=None, timeout=None: FakeResp())
    monkeypatch.setattr("backend.copernicus.get_settings", lambda: type(
        "S", (), {"copernicus_username": "", "copernicus_password": "",
                  "artifact_root": str(tmp_path)})())

    # download=False: catalog-only path must not need credentials.
    resp = client.post("/v1/copernicus/ingest", headers=DEV, json={
        "project_id": pid, "aoi_id": aoi_id,
        "start": "2026-08-01T00:00:00.000Z", "end": "2026-09-01T00:00:00.000Z",
        "download": False,
    })
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "catalog_only"

    # Seed the scene as already registered; re-run must skip, not duplicate.
    fake_db.scenes["seeded"] = {"id": "seeded", "provider_product_id": PRODUCT_NAME}
    resp = client.post("/v1/copernicus/ingest", headers=DEV, json={
        "project_id": pid, "aoi_id": aoi_id,
        "start": "2026-08-01T00:00:00.000Z", "end": "2026-09-01T00:00:00.000Z",
        "download": False,
    })
    assert resp.json()["results"][0]["status"] == "already_registered"
    assert resp.json()["results"][0]["scene_id"] == "seeded"
