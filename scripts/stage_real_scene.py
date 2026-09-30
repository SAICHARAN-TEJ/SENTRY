"""Stage a real Copernicus Sentinel-2 L2A product as a scene in Postgres.

A job submitted with an AOI only decodes that AOI's window of each band
(``worker/rasterio_io.py``), but a scene still has to be staged before any job
can reference it — and a full 10980x10980 L2A tile is thousands of diffusion
windows even when clipped. For a runtime-bounded *local* demo this script
writes a real spatial **window** of the genuine product instead of the whole
tile; the job then clips further to its AOI.

Honesty rules this script follows:
  * the bytes come from the MD5-verified official SAFE zip, verified again here;
  * the window is encoded in every band object key, so a staged subset is never
    mistakable for the full tile;
  * the scene keeps the TRUE provider product id, sensing time, cloud cover,
    CRS and processing baseline;
  * ``scenes.footprint`` is the footprint of the *staged subset*, computed from
    the window transform — not the full tile's footprint, which the subset does
    not cover.

Usage
-----
    python scripts/stage_real_scene.py \
        --product-id 0ad3fe38-5b2a-46c9-9c93-08e22084b52b \
        --zip data/copernicus/0ad3fe38-5b2a-46c9-9c93-08e22084b52b.zip \
        --md5 c87bd6943db17c619567bacf0f392f47 \
        --window 512 --col-off 4600 --row-off 4600
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402
import rasterio  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import Window  # noqa: E402
from shapely.geometry import box  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402

from backend import ingest  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.copernicus import (ODATA_URL, PRODUCT_NAME_RE, USER_AGENT,  # noqa: E402
                                CatalogProduct, extract_bands)

CHUNK = 1 << 20


def md5_file(path: Path) -> str:
    """Streamed MD5 so ~1 GB products never sit in memory."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_product(product_id: str) -> CatalogProduct:
    """Read the official catalogue record for one product id."""
    resp = httpx.get(
        f"{ODATA_URL}/Products({product_id})",
        params={"$expand": "Attributes"},
        timeout=90.0,
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code != 200:
        raise SystemExit(f"catalogue returned HTTP {resp.status_code} for {product_id}")
    try:
        return CatalogProduct.from_odata(resp.json())
    except Exception as exc:  # noqa: BLE001 - a bad catalogue row must stop staging
        raise SystemExit(f"cannot parse catalogue record: {exc}") from exc


def stage_product_window(product_id: str, zip_path: Path, *, window: int = 512,
                         col_off: int = 0, row_off: int = 0,
                         expected_md5: str = "") -> dict:
    """Verify, window and register one real product; returns the staging summary.

    Importable so a driver (the judge demo) can stage on demand instead of
    shelling out and scraping stdout. Raises ``SystemExit`` with a specific
    message when the zip is missing, the checksum disagrees, or the catalogue
    record cannot be read — there is no synthetic fallback.
    """
    if not zip_path.exists():
        raise SystemExit(f"missing SAFE zip: {zip_path}")

    if expected_md5:
        actual = md5_file(zip_path)
        if actual != expected_md5:
            raise SystemExit(f"MD5 mismatch: expected {expected_md5}, got {actual}")
        print(f"zip MD5 verified: {actual}")

    product = fetch_product(product_id)
    print(f"product : {product.name}")
    print(f"sensing : {product.sensing_time.isoformat()}  cloud={product.cloud_pct}%")
    print(f"tile    : {product.tile_id}  online={product.online}")

    bands = extract_bands(str(zip_path))
    root = Path(get_settings().artifact_root)
    size = max(16, int(window))

    object_keys: dict[str, str] = {}
    crs = None
    subset_wkt = None
    res_m = None
    window_px: list[int] | None = None

    for band in ingest.BANDS:
        with rasterio.open(io.BytesIO(bands[band])) as src:
            if int(col_off) < 0 or int(row_off) < 0 or int(col_off) >= src.width or int(row_off) >= src.height:
                raise SystemExit(f"window origin ({col_off},{row_off}) outside raster {src.width}x{src.height}")
            c_off = max(0, min(int(col_off), src.width - 1))
            r_off = max(0, min(int(row_off), src.height - 1))
            w = min(size, src.width - c_off)
            h = min(size, src.height - r_off)
            if w < 16 or h < 16:
                raise SystemExit(f"window too small ({w}x{h}); check col_off/row_off/size")
            window = Window(c_off, r_off, w, h)
            data = src.read(1, window=window)
            win_transform = src.window_transform(window)
            band_crs = src.crs
            res_m = abs(src.res[0])

            # A subset must not be mistakable for the full tile: the window is
            # part of the object key that lands in scene_bands.object_key.
            key = (f"copernicus/{product.name}/"
                   f"{product.tile_id}_{band}_{r_off}x{c_off}_{h}x{w}.tif")
            dest = root / "scene-assets" / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            profile = {
                "driver": "GTiff", "height": h, "width": w, "count": 1,
                "dtype": data.dtype, "crs": band_crs, "transform": win_transform,
                "compress": "deflate",
            }
            with rasterio.open(dest, "w", **profile) as out:
                out.write(data, 1)

            if crs is None:
                crs = band_crs
                window_px = [c_off, r_off, w, h]
                poly = box(win_transform.c, win_transform.f,
                           win_transform.c + win_transform.a * w,
                           win_transform.f + win_transform.e * h)
                if str(band_crs).upper() not in ("EPSG:4326", "WGS84"):
                    tr = Transformer.from_crs(band_crs, "EPSG:4326", always_xy=True)
                    poly = shp_transform(tr.transform, poly)
                minx, miny, maxx, maxy = poly.bounds
                subset_wkt = (f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},"
                              f"{minx} {maxy},{minx} {miny}))")
            object_keys[band] = key
            print(f"  staged {band}  {h}x{w} px -> {key}  ({dest.stat().st_size/1e6:.1f} MB)")

    match = PRODUCT_NAME_RE.match(product.name)
    baseline = f"s2-processing-baseline-{match['baseline']}" if match else "unknown"

    registered = ingest.register_scene(
        provider_product_id=product.name,
        band_object_keys=object_keys,
        footprint_wkt_4326=subset_wkt,
        sensing_time=product.sensing_time,
        cloud_pct=product.cloud_pct,
        crs=str(crs),
        resolution_m=res_m or 10.0,
        source_name="sentinel-2-l2a",
        source_version=baseline,
    )

    return {
        "scene_id": registered["scene_id"],
        "product_name": product.name,
        "product_id": product.product_id,
        "sensing_time": product.sensing_time.isoformat(),
        "cloud_pct": product.cloud_pct,
        "tile_id": product.tile_id,
        "crs": str(crs),
        "resolution_m": res_m,
        "footprint_wkt_4326": subset_wkt,
        "window_px": window_px,
        "object_keys": object_keys,
        "dataset_version": baseline,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product-id", required=True)
    ap.add_argument("--zip", required=True, dest="zip_path")
    ap.add_argument("--md5", default="", help="expected MD5 of the SAFE zip")
    ap.add_argument("--window", type=int, default=512, help="window size in pixels")
    ap.add_argument("--col-off", type=int, default=0)
    ap.add_argument("--row-off", type=int, default=0)
    args = ap.parse_args()

    staged = stage_product_window(
        args.product_id, Path(args.zip_path), window=args.window,
        col_off=args.col_off, row_off=args.row_off, expected_md5=args.md5)

    print()
    print(f"scene_id        : {staged['scene_id']}")
    print(f"dataset version : {staged['dataset_version']}")
    print(f"staged CRS      : {staged['crs']}   resolution: {staged['resolution_m']} m")
    print(f"subset footprint: {staged['footprint_wkt_4326']}")
    print()
    print("NOTE: this scene is a spatial SUBSET of the named product, staged for a")
    print("runtime-bounded local run. The object keys above encode the window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
