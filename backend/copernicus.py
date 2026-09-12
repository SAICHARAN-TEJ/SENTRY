"""Copernicus Data Space Ecosystem connector (PRD Table 3, Layer 1).

Search is anonymous (OData catalogue). Product download uses the authenticated
HTTP path only when COPERNICUS_USERNAME/COPERNICUS_PASSWORD are configured — a
free registered account is required by the Data Space, so downloads fail with a
stable error code until credentials exist (fail-closed, never anonymous-wget).

Band staging follows PRD §6.1: register the L2A product, extract the native
10 m B02/B03/B04/B08 JP2 rasters from the SAFE zip, store them under
``{ARTIFACT_ROOT}/scene-assets/{object_key}``, then register scene + scene_bands
rows via ``ingest.register_scene`` with the provider product id, sensing time,
cloud cover, CRS and footprint — everything downstream provenance expects.
"""

from __future__ import annotations

import hashlib
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from backend import db, ingest
from backend.config import get_settings
from backend.errors import ApiError, DATA_CORRUPT, INVALID_AOI

ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# The catalogue's request filter rejects default scripting-library User-Agents
# (HTTP 403 "violation" observed with python-httpx on 2026-09-12); identify the
# client honestly on every call instead.
USER_AGENT = ("Sentry-SIH26142/0.1 "
              "(Copernicus S2 super-resolution validation research; "
              "https://github.com/SAICHARAN-TEJ/SENTRY)")

BANDS = ingest.BANDS  # ["B02", "B03", "B04", "B08"]

# S2 MSIL2A product naming:
# S2x_MSIL2A_YYYYMMDDTHHMMSS_Nxxxx_Rxxx_Txxxxx_YYYYMMDDTHHMMSS.SAFE
PRODUCT_NAME_RE = re.compile(
    r"^(?P<sat>S2[AB])_MSIL2A_(?P<sensing>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_R(?P<orbit>\d{3})_T(?P<tile>\d{2}[A-Z]{3})_"
    r"\d{8}T\d{6}\.SAFE$"
)

# Band raster paths inside the SAFE zip (10 m native resolution). Two verified
# layouts exist: legacy ``Txxxxx_..._B02.jp2`` and current-baseline
# ``Txxxxx_..._B02_10m.jp2`` (observed on N0512, 2026-09-12) — accept both.
BAND_JP2_RE = re.compile(
    r"GRANULE/[^/]+/IMG_DATA/R10m/[^/]*_B(?P<band>02|03|04|08)(?:_10m)?\.jp2$"
)


@dataclass
class CatalogProduct:
    """One catalogue result, parsed into the fields ingest.register_scene needs."""

    product_id: str
    name: str
    sensing_time: datetime
    tile_id: str
    satellite: str
    online: bool
    footprint_wkt: str | None = None
    cloud_pct: float | None = None
    crs: str = "EPSG:4326"
    resolution_m: float = 10.0

    @classmethod
    def from_odata(cls, row: dict) -> CatalogProduct:
        name = row.get("Name", "")
        match = PRODUCT_NAME_RE.match(name)
        if not match:
            raise ApiError(DATA_CORRUPT, f"unrecognized Sentinel-2 product name: {name}")
        footprint = _footprint_wkt(row)
        return cls(
            product_id=row["Id"],
            name=name,
            sensing_time=datetime.strptime(match["sensing"], "%Y%m%dT%H%M%S"),
            tile_id=match["tile"],
            satellite=match["sat"],
            online=bool(row.get("Online", False)),
            footprint_wkt=footprint,
            cloud_pct=_cloud_cover_pct(row),
        )

    @property
    def baseline_version(self) -> str:
        """Processing baseline (N0512 etc.) as the dataset_sources version string."""
        match = PRODUCT_NAME_RE.match(self.name)
        return f"s2-processing-baseline-{match['baseline']}" if match else "unknown"


def _footprint_wkt(row: dict) -> str | None:
    """Extract GeoJSON footprint -> WKT POLYGON (4326)."""
    geo = row.get("GeoFootprint")
    if not geo or geo.get("type") != "Polygon":
        return None
    rings = geo.get("coordinates") or []
    if not rings or not rings[0]:
        return None
    pts = ", ".join(f"{p[0]} {p[1]}" for p in rings[0])
    return f"POLYGON(({pts}))"


def _cloud_cover_pct(row: dict) -> float | None:
    """cloudCover from the expanded Attributes list (lowercase name, verified
    live 2026-09-12); None when the catalogue does not report it."""
    for attr in row.get("Attributes") or []:
        if attr.get("Name") == "cloudCover":
            try:
                return float(attr.get("Value"))
            except (TypeError, ValueError):
                return None
    return None


# --------------------------------------------------------------------------- #
# Search (anonymous)
# --------------------------------------------------------------------------- #

def search_products(aoi_wkt: str, start: str, end: str,
                    max_cloud: float | None = None, top: int = 20) -> list[CatalogProduct]:
    """Query the OData catalogue for L2A products intersecting an AOI WKT polygon.

    Args are ISO datetimes (start/end) and a 4326 polygon WKT. Returns parsed
    CatalogProduct records ordered by sensing time (newest first upstream).

    Cloud ceiling is applied client-side over ``$expand=Attributes``: the
    catalogue rejected every server-side ``Attributes/any(...)`` shape during
    live verification (2026-09-12), while expanded ``cloudCover`` values work.
    Products whose cloud cover the catalogue does not report are kept — missing
    evidence is surfaced to the caller, never silently hidden.
    """
    if "POLYGON" not in aoi_wkt.upper():
        raise ApiError(INVALID_AOI, "aoi_wkt must be a POLYGON WKT in EPSG:4326")
    top = max(1, min(int(top), 100))

    query = {
        "$filter": " and ".join([
            "Collection/Name eq 'SENTINEL-2'",
            "contains(Name,'MSIL2A')",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi_wkt}')",
            f"ContentDate/Start gt {start}",
            f"ContentDate/Start lt {end}",
        ]),
        "$top": top,
        "$orderby": "ContentDate/Start desc",
        "$expand": "Attributes",
    }
    try:
        resp = httpx.get(f"{ODATA_URL}/Products", params=query, timeout=30.0,
                         headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError as exc:
        raise ApiError(DATA_CORRUPT, f"Copernicus catalogue unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise ApiError(DATA_CORRUPT,
                       f"Copernicus catalogue returned HTTP {resp.status_code}")

    products: list[CatalogProduct] = []
    for row in resp.json().get("value", []):
        try:
            product = CatalogProduct.from_odata(row)
        except ApiError:
            continue  # skip unrecognized names rather than failing the whole search
        if max_cloud is not None and product.cloud_pct is not None \
                and product.cloud_pct > float(max_cloud):
            continue
        products.append(product)
    return products


# --------------------------------------------------------------------------- #
# Download (authenticated, fail-closed)
# --------------------------------------------------------------------------- #

def _access_token(username: str, password: str) -> str:
    """Exchange CDSE credentials for a short-lived access token."""
    resp = httpx.post(
        AUTH_URL,
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": "cdse-public",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise ApiError(DATA_CORRUPT,
                       f"Copernicus authentication failed (HTTP {resp.status_code})")
    token = resp.json().get("access_token")
    if not token:
        raise ApiError(DATA_CORRUPT, "Copernicus auth returned no access token")
    return token


def download_product(product_id: str, dest_dir: str | None = None) -> str:
    """Stream one product SAFE zip to the artifact root; returns the local path.

    Requires COPERNICUS_USERNAME/COPERNICUS_PASSWORD; raises DATA_CORRUPT with
    an actionable message otherwise.    ~1 GB products stream in 1 MiB chunks.
    """
    settings = get_settings()
    root = dest_dir or str(settings.artifact_root)
    path = Path(root) / "scene-assets" / "copernicus" / f"{product_id}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return str(path)  # resumable: already downloaded — no credentials needed

    username, password = settings.copernicus_username, settings.copernicus_password
    if not username or not password:
        raise ApiError(
            DATA_CORRUPT,
            "Copernicus download requires a free CDSE account: set "
            "COPERNICUS_USERNAME and COPERNICUS_PASSWORD (see SOURCES.md)",
        )

    token = _access_token(username, password)
    _stream_download(product_id, path, token)
    return str(path)


def _stream_download(product_id: str, path: Path, token: str) -> str:
    """Stream the product zip to ``path``; returns the computed MD5 hexdigest."""
    try:
        with httpx.stream(
            "GET", DOWNLOAD_URL.format(product_id=product_id),
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
            timeout=httpx.Timeout(3600.0, connect=30.0),
            follow_redirects=True,
        ) as resp:
            if resp.status_code != 200:
                raise ApiError(DATA_CORRUPT,
                               f"Copernicus download failed (HTTP {resp.status_code})")
            digest = hashlib.md5()
            with open(path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1 << 20):
                    fh.write(chunk)
                    digest.update(chunk)
    except httpx.HTTPError as exc:
        # Discard partial file so a retry starts clean.
        path.unlink(missing_ok=True)
        raise ApiError(DATA_CORRUPT, f"Copernicus download failed: {exc}") from exc
    return digest.hexdigest()


def fetch_product_checksum(product_id: str) -> str:
    """Official MD5 hexdigest for a product, from the catalogue (fail-closed:
    a product without a reported checksum is refused rather than trusted)."""
    try:
        resp = httpx.get(f"{ODATA_URL}/Products({product_id})",
                         headers={"User-Agent": USER_AGENT}, timeout=30.0)
    except httpx.HTTPError as exc:
        raise ApiError(DATA_CORRUPT,
                       f"Copernicus catalogue unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise ApiError(DATA_CORRUPT,
                       f"Copernicus catalogue returned HTTP {resp.status_code}")
    for entry in resp.json().get("Checksum") or []:
        if str(entry.get("Algorithm", "")).upper().endswith("MD5"):
            return str(entry.get("Value", "")).lower()
    raise ApiError(DATA_CORRUPT,
                   f"catalogue reported no MD5 checksum for {product_id}; "
                   "refusing to stage an unverified product")


def download_product_verified(product_id: str,
                              dest_dir: str | None = None) -> tuple[str, str]:
    """Download one product and verify it against the catalogue's official MD5.

    Returns ``(path, md5_hex)``. On mismatch the file is deleted and DATA_CORRUPT
    raised — a corrupted transfer can never reach band staging (PRD Phase 0 rule:
    all source artifacts checksummed before use).
    """
    root = dest_dir or str(get_settings().artifact_root)
    path = Path(root) / "scene-assets" / "copernicus" / f"{product_id}.zip"
    if not (path.exists() and path.stat().st_size > 0):
        download_product(product_id, dest_dir)
    expected = fetch_product_checksum(product_id)
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        path.unlink(missing_ok=True)
        raise ApiError(DATA_CORRUPT,
                       f"product {product_id} failed checksum verification "
                       f"({digest.hexdigest()} != {expected}); file deleted")
    return str(path), expected


# --------------------------------------------------------------------------- #
# Band extraction + staging
# --------------------------------------------------------------------------- #

def extract_bands(safe_zip_path: str) -> dict[str, bytes]:
    """Pull the four native 10 m band rasters out of the SAFE zip.

    Returns {band_name: jp2_bytes}. Missing or duplicate bands raise DATA_CORRUPT
    — a product without complete 10 m B02/B03/B04/B08 is never staged (PRD §8).
    """
    bands: dict[str, bytes] = {}
    with zipfile.ZipFile(safe_zip_path) as zf:
        for info in zf.infolist():
            match = BAND_JP2_RE.search(info.filename.replace("\\", "/"))
            if match is None:
                continue
            band = f"B{match['band']}"
            if band in bands:
                raise ApiError(DATA_CORRUPT,
                               f"duplicate 10m band raster for {band} in SAFE zip")
            with zf.open(info) as fh:
                bands[band] = fh.read()
    missing = [b for b in BANDS if b not in bands]
    if missing:
        raise ApiError(DATA_CORRUPT,
                       f"SAFE zip missing 10m bands {missing}; cannot stage scene")
    return bands


def ingest_product(product: CatalogProduct, safe_zip_path: str) -> dict:
    """Extract bands to local storage and register scene + band rows idempotently."""
    import rasterio

    bands = extract_bands(safe_zip_path)
    root = get_settings().artifact_root

    # Derive scene CRS + transform from the first band raster (they share a grid).
    with rasterio.open(io.BytesIO(bands[BANDS[0]])) as first:
        crs = first.crs.to_string() if first.crs else "EPSG:4326"
        transform = [first.transform.a, first.transform.b, first.transform.c,
                     first.transform.d, first.transform.e, first.transform.f]
        width, height = first.width, first.height
        res_x, res_y = first.res

    # Cross-check every band sits on the same grid (cheap integrity gate).
    def _t(aff) -> tuple:
        return (aff.a, aff.b, aff.c, aff.d, aff.e, aff.f)

    for band in BANDS[1:]:
        with rasterio.open(io.BytesIO(bands[band])) as src:
            if (src.width, src.height) != (width, height) or \
                    not all(abs(x - y) < 1e-9 for x, y in
                            zip(_t(src.transform), _t(first.transform))):
                raise ApiError(DATA_CORRUPT,
                               f"band {band} grid mismatch in product {product.name}")

    object_keys: dict[str, str] = {}
    for band in BANDS:
        # PRD §6.1: retain product id, tile and band in the object key.
        key = f"copernicus/{product.name}/{product.tile_id}_{band}.jp2"
        local = Path(root) / "scene-assets" / key
        local.parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as fh:
            fh.write(bands[band])
        object_keys[band] = key

    # PRD §6.1: retain the processing baseline (N0512 etc.) as the dataset version.
    match = PRODUCT_NAME_RE.match(product.name)
    baseline = f"s2-processing-baseline-{match['baseline']}" if match else "unknown"
    registered = ingest.register_scene(
        provider_product_id=product.name,
        band_object_keys=object_keys,
        footprint_wkt_4326=product.footprint_wkt or "POLYGON((0 0,0 0,0 0,0 0))",
        sensing_time=product.sensing_time,
        cloud_pct=product.cloud_pct,
        crs=crs,
        resolution_m=abs(res_x) if res_x else product.resolution_m,
        source_name="sentinel-2-l2a",
        source_version=baseline,
    )
    return {
        "scene_id": registered["scene_id"],
        "band_ids": registered["band_ids"],
        "product": product.name,
        "tile_id": product.tile_id,
        "crs": crs,
        "transform": transform,
        "band_object_keys": object_keys,
    }


def search_and_ingest(aoi_wkt: str, start: str, end: str,
                      max_cloud: float | None = None, top: int = 5,
                      download: bool = True) -> list[dict]:
    """End-to-end: catalogue search -> optional download -> staging -> registration.

    Products already present in ``scenes`` are skipped (idempotent re-runs);
    download failures leave earlier successes intact and are reported per product.
    """
    products = search_products(aoi_wkt, start, end, max_cloud=max_cloud, top=top)
    results: list[dict] = []
    for product in products:
        existing = db.query(
            "select id from scenes where provider_product_id = %s",
            (product.name,), one=True)
        if existing is not None:
            results.append({"scene_id": existing["id"], "product": product.name,
                            "status": "already_registered"})
            continue
        if not download:
            results.append({"product": product.name, "tile_id": product.tile_id,
                            "sensing_time": product.sensing_time.isoformat(),
                            "status": "catalog_only"})
            continue
        try:
            zip_path, _md5 = download_product_verified(product.product_id)
            staged = ingest_product(product, zip_path)
            staged["status"] = "ingested"
            results.append(staged)
        except ApiError as exc:
            results.append({"product": product.name, "status": "failed",
                            "error": {"code": exc.code, "message": exc.message}})
    return results
