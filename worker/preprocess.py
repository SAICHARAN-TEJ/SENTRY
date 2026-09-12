"""Scene preprocessing: uint16 DN -> normalized reflectance tensors + masks."""

from __future__ import annotations

import hashlib

import numpy as np

from backend.errors import ApiError, DATA_CORRUPT

BAND_ORDER = ["B02", "B03", "B04", "B08"]


def preprocess(scene: dict) -> dict:
    """Standardize a 4-band scene into [0,1] reflectance with valid mask + fingerprint.

    scene = {"bands": {band: (H, W) uint16}, "valid": (H, W) bool | None,
             "crs": str, "transform": list, "scale_factor": float = 1e-4}
    """
    bands = scene.get("bands", {})
    missing = [b for b in BAND_ORDER if b not in bands]
    if missing:
        raise ApiError(DATA_CORRUPT, f"scene missing bands: {missing}")

    shapes = {b: np.asarray(bands[b]).shape for b in BAND_ORDER}
    if len(set(shapes.values())) != 1:
        raise ApiError(DATA_CORRUPT, f"band shapes misaligned: {shapes}")

    scale = float(scene.get("scale_factor", 1e-4))
    h, w = shapes[BAND_ORDER[0]]

    reflectance = np.zeros((4, h, w), dtype=np.float32)
    for i, b in enumerate(BAND_ORDER):
        dn = np.asarray(bands[b], dtype=np.float64)
        reflectance[i] = np.clip(dn * scale, 0.0, 1.0).astype(np.float32)

    valid = scene.get("valid")
    if valid is None:
        valid = np.ones((h, w), dtype=bool)
    else:
        valid = np.asarray(valid, dtype=bool)
        if valid.shape != (h, w):
            raise ApiError(DATA_CORRUPT, "valid mask shape mismatch")
    reflectance[:, ~valid] = 0.0

    fp_src = "|".join([
        *(f"{b}:{shapes[b]}" for b in BAND_ORDER),
        f"scale:{scale}", f"crs:{scene.get('crs')}",
        f"transform:{scene.get('transform')}",
    ])
    fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()

    return {
        "reflectance": reflectance,
        "valid": valid,
        "meta": {"crs": scene.get("crs"), "transform": scene.get("transform"),
                 "fingerprint": fingerprint, "scale_factor": scale},
    }
