"""Tiling tests: coverage, determinism, stitch roundtrip fidelity."""

from __future__ import annotations

import numpy as np
import pytest

from worker.tiling import extract_tiles, stitch_tiles, tile_grid


def test_tile_grid_covers_full_raster():
    h, w = 700, 900
    grid = tile_grid(h, w, tile=256, overlap=32)
    assert grid, "grid must not be empty"
    for (r0, c0, r1, c1) in grid:
        assert 0 <= r0 < r1 <= h
        assert 0 <= c0 < c1 <= w
    # Union covers every pixel.
    covered = np.zeros((h, w), dtype=bool)
    for (r0, c0, r1, c1) in grid:
        covered[r0:r1, c0:c1] = True
    assert covered.all()


def test_tile_grid_deterministic():
    assert tile_grid(500, 500) == tile_grid(500, 500)


def test_extract_stitch_roundtrip():
    rng = np.random.default_rng(7)
    arr = rng.uniform(0.2, 0.9, size=(4, 300, 260)).astype(np.float32)
    valid = np.ones((300, 260), dtype=bool)
    tiles = extract_tiles(arr, valid, tile=128, overlap=16)
    assert tiles, "tiles must not be empty"
    stitched, sv = stitch_tiles(tiles, (300, 260), bands=4)
    assert stitched.shape == arr.shape

    # No pixel may be dropped (partition of unity guarantees full coverage).
    assert sv.all()
    # Smooth-field case: stitching must reproduce the input everywhere.
    yy, xx = np.mgrid[0:300, 0:260].astype(np.float32)
    smooth = (0.3 + 0.2 * np.sin(xx / 20 + yy / 30))[None].repeat(4, 0).astype(np.float32)
    st2, _ = stitch_tiles(extract_tiles(smooth, valid, tile=128, overlap=16),
                          (300, 260), bands=4)
    assert np.max(np.abs(st2 - smooth)) < 1e-5

    # Random-noise case: interiors exact, overlap bands are bounded blends.
    interiors = np.zeros((300, 260), dtype=bool)
    stride = 128 - 16
    for r0 in range(0, 300 - 16, stride):
        for c0 in range(0, 260 - 16, stride):
            interiors[r0 + 16:min(r0 + 128 - 16, 300), c0 + 16:min(c0 + 128 - 16, 260)] = True
    d = np.abs(stitched - arr)
    assert d[:, interiors].max() < 1e-5          # exclusive interiors: exact
    assert d.max() <= np.ptp(arr) + 1e-6         # seams: bounded, never garbage
    assert (stitched != 0).all()                 # coverage: nothing zeroed out


def test_stitch_respects_nodata():
    arr = np.ones((4, 200, 200), dtype=np.float32)
    valid = np.ones((200, 200), dtype=bool)
    valid[:, 150:] = False  # right third invalid
    arr[:, :, 150:] = 9.9   # garbage in invalid area
    tiles = extract_tiles(arr, valid, tile=128, overlap=16)
    stitched, sv = stitch_tiles(tiles, (200, 200), bands=4)
    assert not sv[:, 160:].any()      # nodata stays nodata
    assert np.allclose(stitched[:, :, 100], 1.0)  # valid area untouched
    assert stitched[:, :, 180].max() == pytest.approx(0.0)  # garbage never leaks in
