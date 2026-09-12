"""Deterministic tiling: feathered overlaps with guaranteed partition of unity."""

from __future__ import annotations

import numpy as np


def tile_grid(h: int, w: int, tile: int = 256, overlap: int = 32) -> list[tuple]:
    """Cover an image with (r0, c0, r1, c1) windows at stride tile-overlap."""
    if tile <= overlap:
        raise ValueError("tile must exceed overlap")
    stride = tile - overlap
    windows: list[tuple] = []
    r0 = 0
    while True:
        r1 = min(r0 + tile, h)
        c0 = 0
        while True:
            c1 = min(c0 + tile, w)
            windows.append((r0, c0, r1, c1))
            if c1 >= w:
                break
            c0 += stride
        if r1 >= h:
            break
        r0 += stride
    return windows


def _ramp(n: int) -> np.ndarray:
    """Linear fade near 0 -> near 1 without zero-weight seam intersections."""
    if n <= 1:
        return np.ones(1, dtype=np.float32)
    return (np.arange(1, n + 1, dtype=np.float32) / float(n + 1))


def extract_tiles(arr: np.ndarray, valid: np.ndarray, tile: int = 256,
                  overlap: int = 32) -> list[dict]:
    """Slice (B, H, W) into tiles carrying feather weights for exact stitching.

    Weights: 1 in each tile's exclusive interior; linear ramps in overlap
    bands only toward sides that have a neighboring tile.
    """
    if arr.ndim != 3:
        raise ValueError("expected (B, H, W)")
    _, h, w = arr.shape
    tiles: list[dict] = []
    for (r0, c0, r1, c1) in tile_grid(h, w, tile, overlap):
        th, tw = r1 - r0, c1 - c0
        ov = min(overlap, th, tw)

        wgt = np.ones((th, tw), dtype=np.float32)
        if ov > 0:
            ramp = _ramp(ov)
            if r0 > 0:            # neighbor above -> fade in at top
                wgt[:ov, :] *= ramp[:, None]
            if r1 < h:            # neighbor below -> fade out at bottom
                wgt[th - ov:, :] *= ramp[::-1][:, None]
            if c0 > 0:            # neighbor left
                wgt[:, :ov] *= ramp[None, :]
            if c1 < w:            # neighbor right
                wgt[:, tw - ov:] *= ramp[::-1][None, :]

        tiles.append({
            "pixels": arr[:, r0:r1, c0:c1].copy(),
            "valid": valid[r0:r1, c0:c1].copy(),
            "weight": wgt,
            "origin": (r0, c0),
            "window": (r0, c0, r1, c1),
        })
    return tiles


def stitch_tiles(tiles: list[dict], shape: tuple[int, int], bands: int = 4) -> tuple:
    """Deterministic blend: partition-of-unity via wsum normalization.

    Interiors (weight 1, single owner) reproduce input exactly; overlap bands
    blend linearly; nodata is preserved via the union of per-tile valid masks.
    """
    h, w = shape
    out = np.zeros((bands, h, w), dtype=np.float32)
    wsum = np.zeros((h, w), dtype=np.float32)
    valid = np.zeros((h, w), dtype=bool)

    for t in tiles:
        r0, c0, r1, c1 = t["window"]
        px = t["pixels"]
        wgt = t.get("weight", np.ones(px.shape[1:], dtype=np.float32))
        tv = t.get("valid")
        if tv is not None:
            wgt = wgt * tv.astype(np.float32)
            valid[r0:r1, c0:c1] |= tv.astype(bool)
        out[:, r0:r1, c0:c1] += px * wgt[None, :, :]
        wsum[r0:r1, c0:c1] += wgt

    # Guarantee partition of unity where any coverage exists: normalize by the
    # sum (never by zero) so corner pixels covered only by faded tile corners
    # still resolve deterministically.
    mask = wsum > 0
    safe = np.where(mask, wsum, 1.0)
    out /= safe[None, :, :]
    out[:, ~mask] = 0.0
    return out, valid
