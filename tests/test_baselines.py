"""Baseline model tests: shapes, determinism, uncertainty proxy behavior."""

from __future__ import annotations

import numpy as np
import pytest

from backend.errors import ApiError
from worker.baselines import run_bicubic, run_custom_mf, run_opensr, uncertainty_proxy


@pytest.fixture(scope="module")
def tile():
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    a = np.stack([
        0.3 + 0.2 * np.sin(xx / 5.0),
        0.4 + 0.2 * np.cos(yy / 7.0),
        0.5 + 0.2 * np.sin((xx + yy) / 9.0),
        0.6 + 0.1 * np.cos((xx - yy) / 11.0),
    ]).astype(np.float32)
    return np.clip(a, 0, 1)


def test_bicubic_shapes(tile):
    up = run_bicubic(tile, scale=4)
    assert up.shape == (4, 64 * 4, 64 * 4)
    assert up.dtype == np.float32


def test_bicubic_deterministic(tile):
    assert np.array_equal(run_bicubic(tile), run_bicubic(tile))


def test_opensr_unavailable_raises():
    with pytest.raises(ApiError) as ei:
        run_opensr(np.zeros((4, 32, 32), dtype=np.float32))
    assert ei.value.code == "MODEL_UNAVAILABLE"
    assert "opensr-model" in ei.value.message


def test_custom_mf_constant_input(tile):
    const = np.full_like(tile, 0.5)
    sr, unc = run_custom_mf([const], scale=4)
    assert sr.shape == (4, 256, 256)
    assert np.allclose(sr, 0.5, atol=1e-4)
    assert float(unc.max()) < 1e-4  # constant image -> near-zero uncertainty


def test_custom_mf_edge_uncertainty_higher(tile):
    sr, unc = run_custom_mf([tile], scale=4)
    assert unc.shape == (1, 256, 256)
    # Interior (smooth) region must be less uncertain than near edges.
    center = unc[0, 100:156, 100:156].mean()
    edge_col = unc[0, :, 0:10].mean()
    assert edge_col >= center - 1e-6


def test_uncertainty_proxy_range(tile):
    unc = uncertainty_proxy(run_bicubic(tile))
    assert unc.shape[0] == 1
    assert unc.min() >= 0.0 and unc.max() <= 1.0
