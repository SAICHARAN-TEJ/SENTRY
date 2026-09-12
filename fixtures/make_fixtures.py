"""Generate the deterministic synthetic Sentinel-2 scene fixture (512x512, 4 bands)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from skimage.draw import disk

BANDS = ["B02", "B03", "B04", "B08"]
H = W = 512
CRS = "EPSG:32633"
TRANSFORM = [10.0, 0.0, 500000.0, 0.0, -10.0, 6000000.0]  # GDAL order


def build_scene(seed: int = 42) -> dict:
    """Smooth gradients + blobs + edges, uint16 DN in [0, 10000]."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.stack([
        3000 + 2000 * np.sin(xx / 64.0) + 1500 * np.cos(yy / 90.0),
        3500 + 1800 * np.cos(xx / 70.0) + 1200 * np.sin(yy / 75.0),
        4000 + 1500 * np.sin((xx + yy) / 100.0),
        4500 + 2200 * np.cos((xx - yy) / 80.0),
    ]).astype(np.float32)  # (4, H, W)

    # Textured blobs (fields).
    for _ in range(12):
        cx, cy = rng.integers(40, W - 40), rng.integers(40, H - 40)
        r = int(rng.integers(15, 60))
        mask = disk((cy, cx), r, shape=(H, W))
        base[:, mask] = (base[:, mask] * rng.uniform(0.6, 1.4)).astype(np.float32)

    base = base + rng.normal(0, 25, base.shape).astype(np.float32)  # subtle noise
    dn = np.clip(base, 0, 10000).astype(np.uint16)

    valid = np.ones((H, W), dtype=bool)
    valid[:4, :] = False  # 2% invalid border
    valid[-4:, :] = False
    return {"bands": {b: dn[i] for i, b in enumerate(BANDS)},
            "valid": valid, "crs": CRS, "transform": TRANSFORM}


def main() -> Path:
    """Write fixtures/scene_fixture.npz."""
    out_dir = Path(__file__).resolve().parent
    scene = build_scene()
    out = out_dir / "scene_fixture.npz"
    np.savez_compressed(
        out,
        bands=np.stack([scene["bands"][b] for b in BANDS]),
        valid=scene["valid"], crs=np.array([scene["crs"]]),
        transform=np.array(scene["transform"]),
    )
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
