"""Validation engine tests: metrics determinism + PASS/CAUTION/FAIL logic."""

from __future__ import annotations

import numpy as np
import pytest

from backend.validation import engine

GEOREF = {"crs": "EPSG:32633", "transform": [10, 0, 500000, 0, -10, 6000000],
          "width": 128, "height": 128, "bounds": [0, 0, 1280, 1280]}


@pytest.fixture(scope="module")
def arr():
    """Smooth deterministic (H, W, 4) array in [0, 1]."""
    yy, xx = np.mgrid[0:128, 0:128].astype(np.float32)
    a = np.stack([
        0.3 + 0.2 * np.sin(xx / 17.0),
        0.4 + 0.2 * np.cos(yy / 23.0),
        0.5 + 0.2 * np.sin((xx + yy) / 29.0),
        0.6 + 0.15 * np.cos((xx - yy) / 19.0),
    ], axis=-1)
    return np.clip(a, 0, 1).astype(np.float32)


def test_identical_arrays_perfect_metrics(arr):
    sr = ref = arr
    sf = engine.spatial_fidelity(sr, ref)
    assert sf["ssim"] > 0.999
    assert np.isinf(sf["psnr"]) or sf["psnr"] > 60
    spec = engine.spectral_fidelity(sr, ref)
    assert spec["sam"] == pytest.approx(0.0, abs=1e-6)
    assert spec["ergas"] == pytest.approx(0.0, abs=1e-4)


def test_observation_consistency_smooth_roundtrip(arr):
    """A bicubic-downsampled-back SR must be nearly consistent with the observation."""
    from skimage.transform import resize

    s2 = np.stack(
        [resize(arr[..., i], (32, 32), anti_aliasing=True, preserve_range=True)
         for i in range(4)], axis=-1).astype(np.float32)
    # SR = observation upsampled back (perfect reconstruction scenario).
    sr = np.stack(
        [resize(s2[..., i], (128, 128), anti_aliasing=True, preserve_range=True)
         for i in range(4)], axis=-1).astype(np.float32)
    res = engine.observation_consistency(sr, s2)
    assert res["rmse_mean"] < 0.02


def test_geometric_mismatch_fails():
    bad = dict(GEOREF, transform=[20, 0, 500000, 0, -20, 6000000])
    out = engine.check_geometric(GEOREF, bad)
    assert out["pass"] is False
    assert "transform" in out["reasons"]


def test_decide_fail_on_bad_geometry():
    geo = {"pass": False, "reasons": ["crs"]}
    dec = engine.decide_overall_status(geo, {"observation_rmse": 0.001})
    assert dec["overall_status"] == "FAIL"


def test_decide_fail_on_missing_metrics():
    geo = {"pass": True, "reasons": []}
    dec = engine.decide_overall_status(geo, {})  # observation_rmse missing
    assert dec["overall_status"] == "FAIL"
    assert any("missing" in r for r in dec["reasons"])


def test_decide_fail_on_consistency_breach():
    geo = {"pass": True, "reasons": []}
    dec = engine.decide_overall_status(geo, {"observation_rmse": 0.2})
    assert dec["overall_status"] == "FAIL"


def test_decide_caution_on_weak_calibration():
    geo = {"pass": True, "reasons": []}
    dec = engine.decide_overall_status(geo, {
        "observation_rmse": 0.01, "used_reference": True,
        "psnr": 30.0, "ssim": 0.9, "sam": 0.05, "error_correlation": 0.05,
        "ref_coverage": 0.95, "valid_coverage": 1.0})
    assert dec["overall_status"] == "CAUTION"
    assert any("calibration" in r for r in dec["reasons"])


def test_decide_pass_clean_case():
    geo = {"pass": True, "reasons": []}
    dec = engine.decide_overall_status(geo, {
        "observation_rmse": 0.005, "used_reference": True,
        "psnr": 32.0, "ssim": 0.95, "sam": 0.02, "error_correlation": 0.6,
        "ref_coverage": 0.99, "valid_coverage": 1.0})
    assert dec["overall_status"] == "PASS"
    assert 0.0 < dec["score"] <= 1.0


def test_benchmark_delta_sign_conventions():
    d = engine.benchmark_delta({"psnr": 28.0, "ssim": 0.9, "sam": 0.1},
                               {"psnr": 24.0, "ssim": 0.8, "sam": 0.2})
    assert d["psnr"]["higher_is_better"] is True
    assert d["psnr"]["improved"] is True
    assert d["sam"]["higher_is_better"] is False
    assert d["sam"]["improved"] is True  # lower sam is better
    assert d["ssim"]["delta"] == pytest.approx(0.1, abs=1e-6)


def test_uncertainty_quality(arr):
    unc = np.abs(arr[..., 0] - 0.5).astype(np.float32)  # (H, W)
    out = engine.uncertainty_quality(unc, arr, ref=None)
    assert 0.0 <= out["mean"] <= 1.0
    assert out["coverage"] > 0.9
    # Without a high-resolution reference, calibration is intentionally not
    # claimed; only the uncertainty distribution and finite-pixel coverage
    # are reported.
    assert out["calibration"] is None
    assert out["error_correlation"] is None


def test_uncertainty_reliability_with_reference(arr):
    unc = np.abs(arr[..., 0] - 0.5).astype(np.float32)
    ref = np.clip(arr + 0.01 * np.sin(np.indices(arr.shape[:2])[0])[..., None], 0, 1)
    out = engine.uncertainty_quality(unc, arr, ref=ref)
    assert out["calibration"] is not None
    assert len(out["calibration"]["reliability_curve"]) > 0
    assert out["calibration"]["n_valid"] > 0


def test_reference_agreement_grid_recorded(arr):
    out = engine.reference_agreement(arr, arr, grid_m=2.5)
    assert out["grid_m"] == 2.5
    assert "anti-aliased resize" in out["resampling"]
    assert out["metrics"]["sam"] == pytest.approx(0.0, abs=1e-6)


def test_standard_sam_is_scale_invariant(arr):
    scaled = arr * 2.0
    spec = engine.spectral_fidelity(arr, scaled)
    assert spec["sam"] == pytest.approx(0.0, abs=1e-6)


def test_nonfinite_observation_fails():
    dec = engine.decide_overall_status(
        {"pass": True, "reasons": []},
        {"observation_rmse": float("nan")},
    )
    assert dec["overall_status"] == "FAIL"
