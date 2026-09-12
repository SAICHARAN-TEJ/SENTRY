"""COG-style GeoTIFF IO: write/read rasters with full georeferencing metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def write_cog(path: str | Path, array: np.ndarray, crs: str, transform: list,
              band_names: list[str], nodata: float | None = None,
              resolution_m: float | None = None) -> str:
    """Write a (B, H, W) array as a compressed tiled GeoTIFF with overviews."""
    import rasterio
    from rasterio.transform import Affine

    if array.ndim != 3:
        raise ValueError("expected (B, H, W)")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # GDAL order [a, b, c, d, e, f] -> Affine(a, b, c, d, e, f)
    a, b, c, d, e, f = (transform + [0, 0, 0])[:6]
    aff = Affine(a, b, c, d, e, f)
    _, h, w = array.shape

    with rasterio.open(
        str(path), "w", driver="GTiff", height=h, width=w, count=array.shape[0],
        dtype="float32", crs=crs, transform=aff, nodata=nodata,
        compress="LZW", tiled=True, blockxsize=256, blockysize=256,
    ) as dst:
        for i in range(array.shape[0]):
            dst.write(array[i], i + 1)
        dst.descriptions = tuple(band_names[: array.shape[0]])
        dst.update_tags(resolution_m=str(resolution_m) if resolution_m else "")
        overviews = [f for f in (2, 4, 8) if min(h, w) // f >= 256]
        if overviews:
            from rasterio.enums import Resampling
            dst.build_overviews(overviews, Resampling.nearest)
    return str(path)


def read_raster(path: str | Path) -> dict:
    """Read a GeoTIFF into engine/worker dict format."""
    import rasterio

    with rasterio.open(str(path)) as src:
        arr = src.read(masked=True).filled(np.nan).astype(np.float32)
        return {
            "array": arr,  # (B, H, W)
            "crs": src.crs.to_string() if src.crs else "",
            # Canonical internal order is Affine(a, b, c, d, e, f), matching
            # write_cog and the fixture contract (not GDAL's c,a,b,f,d,e).
            "transform": [src.transform.a, src.transform.b, src.transform.c,
                          src.transform.d, src.transform.e, src.transform.f],
            "width": src.width,
            "height": src.height,
            "bounds": list(src.bounds),
            "band_names": list(src.descriptions or []),
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
        }


def sha256_file(path: str | Path) -> str:
    """Chunked file checksum."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
