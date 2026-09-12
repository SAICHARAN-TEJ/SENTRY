"""Central Validation Engine (PRD 9): components A-G as pure functions.

Arrays are float32 reflectance in [0, 1] with shape (H, W, 4) in band order
[B02, B03, B04, B08] unless noted. Georef dicts carry {"crs", "transform",
"width", "height", "bounds"}.

Metric conventions:
- All full-reference metrics operate on VALID pixels only (finite, positive
  reflectance); masks propagate through every component.
- SAM uses the standard norm-invariant spectral angle arccos(<a,b>/|a||b|).
- Mandatory metrics must be finite; NaN/inf counts as missing evidence.
"""

from __future__ import annotations

import numpy as np
from skimage.metrics import structural_similarity
from skimage.morphology import erosion
from skimage.transform import resize

BANDS = ["B02", "B03", "B04", "B08"]

# Thresholds applied when the caller does not override (PRD 9.3).
DEFAULT_THRESHOLDS = {
    "observation_rmse_hard": 0.05,   # FAIL above this (reflectance units)
    "ref_coverage_soft": 0.9,        # CAUTION below
    "calib_corr_soft": 0.2,          # CAUTION below
    "ssim_soft": 0.5,                # CAUTION below
    "sam_soft": 0.15,                # CAUTION above (radians)
    "min_ref_coverage": 0.1,         # FAIL below: not enough reference to judge
}

# Documented degradation operator (PRD 9.2). Anti-aliased resampling is a
# generic approximation of the sensor spatial response; the S2 MTF/point-spread
# function is NOT modeled. Recorded in every observation-consistency result.
DEGRADATION_OPERATOR = "anti-aliased resize (generic approximation; S2 MTF not modeled)"


def check_geometric(a: dict, b: dict) -> dict:
    """Component A: CRS, transform, pixel grid, alignment consistency."""
    def same_numeric(left: object, right: object) -> bool:
        try:
            la = np.asarray(left, dtype=float)
            ra = np.asarray(right, dtype=float)
            return la.shape == ra.shape and bool(np.allclose(la, ra))
        except (TypeError, ValueError):
            return False

    checks = {
        "crs": a.get("crs") == b.get("crs"),
        "transform": same_numeric(a.get("transform", []), b.get("transform", [])),
        "width": a.get("width") == b.get("width"),
        "height": a.get("height") == b.get("height"),
        "bounds": same_numeric(a.get("bounds", []), b.get("bounds", [])),
    }
    reasons = [k for k, ok in checks.items() if not ok]
    return {"pass": not reasons, "checks": checks, "reasons": reasons}


def expected_sr_georef(obs_georef: dict, scale: int = 4) -> dict:
    """Derive the expected SR-grid georef from the observation grid (10 m -> 2.5 m)."""
    t = list(np.asarray(obs_georef["transform"], dtype=float))
    w, h = int(obs_georef["width"]), int(obs_georef["height"])
    sr_t = [t[0] / scale, t[1], t[2], t[3], t[4] / scale, t[5]]
    x0, y0 = sr_t[2], sr_t[5]
    x1 = x0 + sr_t[0] * (w * scale)
    y1 = y0 + sr_t[4] * (h * scale)
    return {"crs": obs_georef["crs"], "transform": sr_t, "width": w * scale,
            "height": h * scale,
            "bounds": [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]}


def _valid_mask(sr: np.ndarray, ref: np.ndarray | None = None,
                valid_mask: np.ndarray | None = None) -> np.ndarray:
    """Return the explicit/finite pixel mask used by every full-reference metric.

    Nodata is represented by the caller's mask or NaN after geospatial
    reprojection.  A valid zero-valued reflectance pixel is not silently
    discarded merely because it is dark.
    """
    m = np.isfinite(sr).all(axis=-1)
    if ref is not None:
        m = m & np.isfinite(ref).all(axis=-1)
    if valid_mask is not None:
        m = m & np.asarray(valid_mask, dtype=bool)
    return np.asarray(m, dtype=bool)


def spatial_fidelity(sr: np.ndarray, ref: np.ndarray,
                     valid_mask: np.ndarray | None = None) -> dict:
    """Component B: PSNR/SSIM/optional LPIPS, excluding invalid pixels.

    PSNR is computed directly on valid samples. SSIM is averaged only over
    windows whose full 7x7 support is valid, so nodata is never replaced by a
    synthetic zero observation. LPIPS is omitted when a mask is required
    because the reference implementation has no pixel-mask contract.
    """
    if sr.shape != ref.shape or sr.ndim != 3:
        raise ValueError("spatial_fidelity expects equally shaped (H, W, B) arrays")
    mask = _valid_mask(sr, ref, valid_mask)
    if mask.sum() < 16:
        return {"psnr": None, "ssim": None, "lpips": None,
                "valid_coverage": float(mask.mean())}

    diff = (sr - ref)[mask]
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    psnr = float("inf") if mse == 0.0 else float(10.0 * np.log10(1.0 / mse))

    # structural_similarity returns the local SSIM image with full=True.
    # Fill only pixels outside the support used for the SSIM average.  The
    # erosion excludes every window touching nodata, so synthetic fill values
    # cannot contribute to the reported score.
    sr_filled = np.where(mask[..., None], sr, 0.0)
    ref_filled = np.where(mask[..., None], ref, 0.0)
    min_side = min(sr.shape[0], sr.shape[1])
    win = min(7, min_side if min_side % 2 else min_side - 1)
    if win < 3:
        ssim = None
        ssim_map = None
    else:
        _, ssim_map = structural_similarity(ref_filled, sr_filled,
                                            channel_axis=2, data_range=1.0,
                                            win_size=win, full=True)
    erosion_size = win if ssim_map is not None else 1
    window_mask = erosion(mask, footprint=np.ones((erosion_size, erosion_size),
                                                    dtype=bool))
    if not window_mask.any():
        ssim = None
    elif ssim_map is not None and ssim_map.ndim == 3:
        ssim = float(np.mean(ssim_map[window_mask, :]))
    else:
        ssim = float(np.mean(ssim_map[window_mask]))

    lpips_score = None
    if mask.all():
        try:  # optional perceptual metric; guarded because lpips is heavy
            import torch
            import lpips as lpips_lib

            net = lpips_lib.LPIPS(net="alex")
            with torch.no_grad():
                a = torch.from_numpy(np.moveaxis(sr, -1, 0))[None] * 2 - 1
                b = torch.from_numpy(np.moveaxis(ref, -1, 0))[None] * 2 - 1
                lpips_score = float(net(a, b).item())
        except Exception:  # noqa: BLE001 - optional dependency
            lpips_score = None
    return {"psnr": psnr, "ssim": ssim, "lpips": lpips_score,
            "valid_coverage": float(mask.mean())}


def spectral_fidelity(sr: np.ndarray, ref: np.ndarray,
                      valid_mask: np.ndarray | None = None) -> dict:
    """Component C: per-band RMSE, norm-invariant SAM, ERGAS on valid pixels."""
    if sr.shape != ref.shape or sr.ndim != 3:
        raise ValueError("spectral_fidelity expects equally shaped (H, W, B) arrays")
    mask = _valid_mask(sr, ref, valid_mask)
    out: dict = {"sam": None, "ergas": None, "valid_coverage": float(mask.mean())}
    if mask.sum() < 16:
        for b in BANDS:
            out[f"rmse_{b}"] = None
        return out

    h = 4.0  # resolution ratio 10 m -> 2.5 m
    rmse_bands, ref_means = [], []
    for i, band in enumerate(BANDS):
        d = (sr[..., i] - ref[..., i])[mask]
        out[f"rmse_{band}"] = float(np.sqrt(np.mean(d ** 2)))
        rmse_bands.append(out[f"rmse_{band}"])
        ref_means.append(float(np.mean(ref[..., i][mask])))

    # Standard SAM: arccos(<a,b> / (|a||b|)) — norm-invariant.
    eps = 1e-12
    a = np.clip(sr, 0, None).astype(np.float64)[mask] + eps
    b = np.clip(ref, 0, None).astype(np.float64)[mask] + eps
    na, nb = a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), eps), \
        b / np.maximum(np.linalg.norm(b, axis=-1, keepdims=True), eps)
    cos = np.clip(np.sum(na * nb, axis=-1), -1.0, 1.0)
    out["sam"] = float(np.mean(np.arccos(cos)))

    # ERGAS: 100/h * sqrt(mean((RMSE_b / mean_b)^2)); zero-mean bands excluded.
    usable = [(r, m) for r, m in zip(rmse_bands, ref_means) if m > 1e-6]
    if usable:
        ratios = np.array([r / m for r, m in usable])
        out["ergas"] = float(100.0 / h * np.sqrt(np.mean(ratios ** 2)))
    return out


def observation_consistency(sr: np.ndarray, s2: np.ndarray,
                            valid_mask: np.ndarray | None = None) -> dict:
    """Component D: documented degradation of SR vs the original S2 grid."""
    down = np.stack(
        [resize(sr[..., i], s2.shape[:2], anti_aliasing=True, preserve_range=True)
         for i in range(sr.shape[2])],
        axis=-1,
    ).astype(np.float32)
    valid = np.isfinite(s2).all(axis=-1) & np.isfinite(down).all(axis=-1)
    if valid_mask is not None:
        valid &= np.asarray(valid_mask, dtype=bool)
    per_band: dict = {}
    residuals = np.zeros_like(s2, dtype=np.float32)
    for i, band in enumerate(BANDS):
        diff = (down[..., i] - s2[..., i])
        residuals[..., i] = np.where(valid, diff, 0.0)
        if valid.any():
            v = diff[valid]
            per_band[band] = {"rmse": float(np.sqrt(np.mean(v ** 2))),
                              "mean": float(np.mean(v)), "std": float(np.std(v))}
        else:
            per_band[band] = {"rmse": None, "mean": None, "std": None}
    finite_rmses = [per_band[b]["rmse"] for b in BANDS
                    if per_band[b]["rmse"] is not None]
    rmse_mean = float(np.mean(finite_rmses)) if finite_rmses else None
    return {"per_band": per_band, "rmse_mean": rmse_mean,
            "residual_map": residuals, "valid_coverage": float(valid.mean()),
            "operator": DEGRADATION_OPERATOR}


def reference_agreement(sr: np.ndarray, ref: np.ndarray, grid_m: float,
                        valid_mask: np.ndarray | None = None) -> dict:
    """Component E: comparison of arrays already on one geospatial grid.

    CRS/affine-aware reprojection belongs to validation.runner; silently
    resizing here would allow same-shaped rasters from different places to be
    compared as if aligned.
    """
    if ref.shape[:2] != sr.shape[:2]:
        raise ValueError("reference must be geospatially aligned to the SR grid first")
    spatial = spatial_fidelity(sr, ref, valid_mask)
    spectral = spectral_fidelity(sr, ref, valid_mask)
    return {"grid_m": float(grid_m), "resampling": DEGRADATION_OPERATOR,
            "metrics": {**spatial, **spectral}}


def uncertainty_quality(unc: np.ndarray, sr: np.ndarray,
                         ref: np.ndarray | None = None,
                         valid_mask: np.ndarray | None = None) -> dict:
    """Component F: coverage, percentiles, reliability diagnostics.

    ``coverage`` = fraction of FINITE uncertainty pixels (valid observation),
    not fraction of positive values. Calibration: when a reference is given,
    a decile reliability curve (mean uncertainty vs mean realized error per
    uncertainty decile) plus error correlation; nominal-level CDFs of
    uncertainty alone do NOT measure calibration and are reported separately
    only as the uncertainty distribution.
    """
    finite = np.isfinite(unc)
    if valid_mask is not None:
        finite &= np.asarray(valid_mask, dtype=bool)
    flat = unc[finite]
    out: dict = {
        "mean": float(np.mean(flat)) if flat.size else 0.0,
        "p50": float(np.percentile(flat, 50)) if flat.size else 0.0,
        "p90": float(np.percentile(flat, 90)) if flat.size else 0.0,
        "p95": float(np.percentile(flat, 95)) if flat.size else 0.0,
        "max": float(np.max(flat)) if flat.size else 0.0,
        "coverage": float(finite.mean()),
        "calibration": None,
        "error_correlation": None,
    }
    if ref is not None and sr.shape[:2] == ref.shape[:2] and unc.shape == sr.shape[:2]:
        err = np.abs(sr - ref).mean(axis=2)
        m = finite & np.isfinite(err)
        if m.sum() > 2 and np.std(unc[m]) > 0 and np.std(err[m]) > 0:
            out["error_correlation"] = float(np.corrcoef(unc[m], err[m])[0, 1])
            # Decile reliability curve: does higher uncertainty carry higher error?
            q = np.quantile(unc[m], np.linspace(0, 1, 11))
            q[0] -= 1e-9
            bins = np.clip(np.digitize(unc[m], q) - 1, 0, 9)
            curve = [{"decile": k,
                      "mean_uncertainty": float(np.mean(unc[m][bins == k])),
                      "mean_abs_error": float(np.mean(err[m][bins == k]))}
                     for k in range(10) if (bins == k).any()]
            out["calibration"] = {"reliability_curve": curve,
                                  "n_valid": int(m.sum())}
    return out


def benchmark_delta(custom: dict, baseline: dict) -> dict:
    """Component G: per-metric deltas on identical tiles (sign conventions)."""
    higher_is_better = {"psnr", "ssim"}
    deltas: dict = {}
    for key in set(custom) & set(baseline):
        c, b = custom[key], baseline[key]
        if c is None or b is None:
            continue
        c, b = float(c), float(b)
        if not (np.isfinite(c) and np.isfinite(b)):
            continue
        deltas[key] = {
            "custom": c, "baseline": b, "delta": c - b,
            "higher_is_better": key in higher_is_better,
            "improved": (c > b) if key in higher_is_better else (c < b),
        }
    return deltas


def _finite_or_none(value, *, allow_pos_inf: bool = False) -> float | None:
    """None for non-finite values; mandatory-metric logic treats them as missing."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(v) or (not allow_pos_inf and not np.isfinite(v)):
        return None
    if allow_pos_inf and np.isneginf(v):
        return None
    return v


def decide_overall_status(geometric: dict, metrics: dict,
                          thresholds: dict | None = None) -> dict:
    """PRD 9.3 decision: PASS / CAUTION / FAIL plus a [0,1] score.

    Mandatory metrics must be present AND finite; NaN/inf counts as missing
    evidence and fails the run.
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    reasons: list[str] = []

    if not geometric.get("pass", False):
        reasons.append(f"geometric check failed: {geometric.get('reasons')}")

    obs_rmse = _finite_or_none(metrics.get("observation_rmse"))
    if obs_rmse is None:
        reasons.append("mandatory observation-consistency metric missing or non-finite")
    elif obs_rmse > th["observation_rmse_hard"]:
        reasons.append(f"observation consistency rmse {obs_rmse:.4f} > hard threshold")

    used_ref = metrics.get("used_reference", False)
    if used_ref:
        for key in ("psnr", "ssim", "sam"):
            if _finite_or_none(metrics.get(key), allow_pos_inf=(key == "psnr")) is None:
                reasons.append(f"mandatory reference metric missing or non-finite: {key}")
        cov = _finite_or_none(metrics.get("ref_coverage"))
        if cov is not None and cov < th["min_ref_coverage"]:
            reasons.append(f"reference coverage {cov:.3f} below minimum")

    if reasons:
        return {"overall_status": "FAIL", "score": 0.0, "reasons": reasons,
                "thresholds_applied": th}

    cautions: list[str] = []
    cov = _finite_or_none(metrics.get("ref_coverage"))
    if used_ref and cov is not None and cov < th["ref_coverage_soft"]:
        cautions.append("reference coverage below soft threshold")
    corr = _finite_or_none(metrics.get("error_correlation"))
    if used_ref and corr is not None and corr < th["calib_corr_soft"]:
        cautions.append(f"uncertainty calibration weak (corr={corr:.3f})")
    ssim = _finite_or_none(metrics.get("ssim"))
    if used_ref and ssim is not None and ssim < th["ssim_soft"]:
        cautions.append(f"ssim below soft threshold ({ssim:.3f})")
    sam = _finite_or_none(metrics.get("sam"))
    if used_ref and sam is not None and sam > th["sam_soft"]:
        cautions.append(f"sam above soft threshold ({sam:.3f})")

    # Score: normalized blend of available components.
    parts: list[float] = []
    if ssim is not None:
        parts.append(float(np.clip(ssim, 0, 1)))
    if sam is not None:
        parts.append(float(np.clip(1.0 - sam / (np.pi / 4.0), 0, 1)))
    vcov = _finite_or_none(metrics.get("valid_coverage"))
    if vcov is not None:
        parts.append(float(np.clip(vcov, 0, 1)))
    score = round(float(np.mean(parts)), 3) if parts else 0.5

    status = "CAUTION" if cautions else "PASS"
    return {"overall_status": status, "score": score,
            "reasons": cautions or ["all checks passed"], "thresholds_applied": th}
