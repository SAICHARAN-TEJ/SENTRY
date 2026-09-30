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
    "calib_corr_ok": 0.4,            # "calibrated" at or above
    "calib_monotonicity_ok": 0.5,    # decile rank correlation for "calibrated"
    "ssim_soft": 0.5,                # CAUTION below
    "sam_soft": 0.15,                # CAUTION above (radians)
    "min_ref_coverage": 0.1,         # FAIL below: not enough reference to judge
    "valid_coverage_soft": 0.5,      # CAUTION below
    "uncertainty_coverage_soft": 0.9,  # CAUTION below
}

# Status vocabulary shared by every gate check and the UI.
PASS, CAUTION, FAIL, NOT_EVALUATED = "PASS", "CAUTION", "FAIL", "NOT_EVALUATED"


def json_safe(obj):
    """Recursively replace non-finite floats (NaN/inf) with None.

    Python's json module serializes inf as the literal ``Infinity``, which is
    not valid JSON: strict parsers (including the browser's JSON.parse used by
    the console) reject the whole report. Engine metrics legitimately contain
    inf (PSNR of identical images), so every report boundary must pass through
    here before ``json.dumps``.
    """
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj

# Documented degradation operator (PRD 9.2). Anti-aliased resampling is a
# generic approximation of the sensor spatial response; the S2 MTF/point-spread
# function is NOT modeled. Recorded in every observation-consistency result.
DEGRADATION_OPERATOR = "anti-aliased resize (generic approximation; S2 MTF not modeled)"

# Missing-evidence policy for a run with no high-resolution reference. Such a
# run collects NO full-reference evidence: spatial/spectral fidelity and
# uncertainty calibration are all NOT_EVALUATED. It still reports observation
# consistency, coverage and uncertainty, but super-resolution accuracy is
# unverified, so it is deliberately never allowed to read as PASS. The verdict
# is CAUTION and this sentence is the reported reason.
NO_REFERENCE_REASON = (
    "no high-resolution reference supplied: super-resolution accuracy is "
    "unverified; this run reports observation consistency and uncertainty only")

# The composite score is a mean of full-reference fidelity terms. With none of
# them computed it would collapse to valid-pixel coverage alone, which reads as
# a near-perfect result for a run whose accuracy was never measured. The score
# is therefore withheld rather than reported.
NO_REFERENCE_SCORE_NOTE = (
    "no full-reference evidence collected, so no composite fidelity score is reported")


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
    if not window_mask.any() or ssim_map is None:
        # No eroded support (or an image too small for any SSIM window):
        # missing evidence, never a subscript into None.
        ssim = None
    elif ssim_map.ndim == 3:
        ssim = float(np.mean(ssim_map[window_mask, :]))
    else:
        ssim = float(np.mean(ssim_map[window_mask]))

    lpips_score = None
    if mask.all() and sr.shape[2] >= 3:
        try:  # optional perceptual metric; guarded because lpips is heavy
            import torch
            import lpips as lpips_lib

            net = lpips_lib.LPIPS(net="alex")
            with torch.no_grad():
                # LPIPS expects 3-channel RGB in [-1, 1]; use B04/B03/B02.
                rgb_idx = [2, 1, 0] if sr.shape[2] >= 3 else list(range(sr.shape[2]))
                a = torch.from_numpy(np.moveaxis(sr[..., rgb_idx], -1, 0))[None] * 2 - 1
                b = torch.from_numpy(np.moveaxis(ref[..., rgb_idx], -1, 0))[None] * 2 - 1
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
    if sr.ndim != 3 or s2.ndim != 3 or sr.shape[2] != s2.shape[2]:
        raise ValueError("observation_consistency expects equally shaped (H, W, B) arrays")
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
    bands = BANDS if s2.shape[2] == len(BANDS) else [f"B{i:02d}" for i in range(s2.shape[2])]
    for i, band in enumerate(bands):
        diff = (down[..., i] - s2[..., i])
        residuals[..., i] = np.where(valid, diff, 0.0)
        if valid.any():
            v = diff[valid]
            per_band[band] = {"rmse": float(np.sqrt(np.mean(v ** 2))),
                              "mean": float(np.mean(v)), "std": float(np.std(v))}
        else:
            per_band[band] = {"rmse": None, "mean": None, "std": None}
    finite_rmses = [per_band[b]["rmse"] for b in bands
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


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    """Rank correlation, dependency-free; ``None`` when undefined."""
    if x.size < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def uncertainty_quality(unc: np.ndarray, sr: np.ndarray,
                         ref: np.ndarray | None = None,
                         valid_mask: np.ndarray | None = None,
                         uncertainty_kind: str | None = None) -> dict:
    """Component F: coverage, percentiles, reliability + calibration verdict.

    ``coverage`` = fraction of FINITE uncertainty pixels (valid observation),
    not fraction of positive values.

    Calibration asks the only question that matters: *do pixels the model is
    unsure about actually have larger reconstruction error?* It is answered by
    the decile reliability curve plus the error correlation, and summarised in
    ``calibration_status``. Uncertainty that is not probabilistic by
    construction (``auxiliary_gradient_indicator``) is never reported as
    calibrated — it is reported as not evaluated, with the reason attached.
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
        "uncertainty_kind": uncertainty_kind,
        "calibration_status": "not_evaluated",
        "calibration_reason": None,
    }
    probabilistic = uncertainty_kind == "stochastic_sampling_std"
    if not probabilistic and uncertainty_kind is not None:
        out["calibration_reason"] = (
            f"{uncertainty_kind} is not a probabilistic uncertainty estimate; "
            "calibration against reconstruction error is not applicable")
        return out

    if ref is None:
        out["calibration_reason"] = "no high-resolution reference available"
        return out
    if not (sr.shape[:2] == ref.shape[:2] and unc.shape == sr.shape[:2]):
        out["calibration_reason"] = "uncertainty/reference/SR grids differ"
        return out

    err = np.abs(sr - ref).mean(axis=2)
    m = finite & np.isfinite(err)
    if m.sum() <= 2 or np.std(unc[m]) <= 0 or np.std(err[m]) <= 0:
        out["calibration_reason"] = "too few valid pixels or no uncertainty spread"
        return out

    out["error_correlation"] = float(np.corrcoef(unc[m], err[m])[0, 1])
    # Decile reliability curve: does higher uncertainty carry higher error?
    q = np.quantile(unc[m], np.linspace(0, 1, 11))
    q[0] -= 1e-9
    bins = np.clip(np.digitize(unc[m], q) - 1, 0, 9)
    curve = [{"decile": k,
              "mean_uncertainty": float(np.mean(unc[m][bins == k])),
              "mean_abs_error": float(np.mean(err[m][bins == k])),
              "n_pixels": int((bins == k).sum())}
             for k in range(10) if (bins == k).any()]
    monotonicity = None
    if len(curve) >= 3:
        monotonicity = _spearman(np.array([c["mean_uncertainty"] for c in curve]),
                                np.array([c["mean_abs_error"] for c in curve]))
    top, bottom = (curve[-1]["mean_abs_error"], curve[0]["mean_abs_error"])
    out["calibration"] = {
        "reliability_curve": curve,
        "n_valid": int(m.sum()),
        "decile_rank_correlation": monotonicity,
        "highest_decile_mean_error": top,
        "lowest_decile_mean_error": bottom,
        "error_ratio_top_over_bottom": (round(top / bottom, 3)
                                        if bottom and bottom > 0 else None),
    }
    ok_corr = out["error_correlation"] >= DEFAULT_THRESHOLDS["calib_corr_ok"]
    ok_mono = (monotonicity is not None
               and monotonicity >= DEFAULT_THRESHOLDS["calib_monotonicity_ok"])
    if ok_corr and ok_mono:
        out["calibration_status"] = "calibrated"
        out["calibration_reason"] = (
            f"uncertainty tracks realized error (r={out['error_correlation']:.3f}, "
            f"decile rank correlation={monotonicity:.3f})")
    else:
        out["calibration_status"] = "weak"
        out["calibration_reason"] = (
            "uncertainty does not reliably track realized error "
            f"(r={out['error_correlation']:.3f}, "
            f"decile rank correlation={monotonicity if monotonicity is None else round(monotonicity, 3)})")
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


def _check(name: str, status: str, detail: str, *,
           value: float | None = None,
           threshold: float | None = None) -> dict:
    """One gate check: what was tested, how it came out, and against what."""
    return {"name": name, "status": status, "detail": detail,
            "value": value, "threshold": threshold}


# UI order for the evidence list (PRD §13 / task §13).
CHECK_ORDER = ["georeferencing", "observation_consistency", "spatial_fidelity",
               "spectral_fidelity", "uncertainty_quality", "reference_coverage",
               "valid_coverage"]


def quality_gate(geometric: dict, metrics: dict,
                 thresholds: dict | None = None) -> dict:
    """PRD 9.3 decision with per-check evidence: PASS / CAUTION / FAIL.

    Mandatory metrics must be present AND finite; NaN/inf counts as missing
    evidence and fails the run. Missing uncertainty fails the run when the
    caller declares ``uncertainty_present=False`` — a reconstruction whose
    uncertainty was never computed can never read as validated.

    A run with no high-resolution reference collects no full-reference evidence
    at all, so it can never read as PASS: the verdict is CAUTION, the missing
    evidence is named as the reason, and the composite ``score`` is withheld
    (``None``) rather than computed from coverage alone. ``score_note`` explains
    the omission.

    Returns ``checks`` alongside the verdict so the UI can show exactly which
    gates passed, which were merely weak, and which failed.
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    checks: list[dict] = []
    fails: list[str] = []
    cautions: list[str] = []

    def add(name, status, detail, value=None, threshold=None):
        checks.append(_check(name, status, detail, value=value, threshold=threshold))
        if status == FAIL:
            fails.append(detail)
        elif status == CAUTION:
            cautions.append(detail)

    # --- georeferencing --------------------------------------------------- #
    if geometric.get("pass", False):
        add("georeferencing", PASS, "CRS, affine transform, grid and bounds agree")
    else:
        add("georeferencing", FAIL,
            f"geometric check failed: {geometric.get('reasons')}")

    # --- observation consistency ----------------------------------------- #
    obs_rmse = _finite_or_none(metrics.get("observation_rmse"))
    if obs_rmse is None:
        add("observation_consistency", FAIL,
            "mandatory observation-consistency metric missing or non-finite")
    elif obs_rmse > th["observation_rmse_hard"]:
        add("observation_consistency", FAIL,
            f"observation consistency rmse {obs_rmse:.4f} > hard threshold",
            obs_rmse, th["observation_rmse_hard"])
    else:
        add("observation_consistency", PASS,
            f"scale-back rmse {obs_rmse:.4f} within tolerance",
            obs_rmse, th["observation_rmse_hard"])

    used_ref = bool(metrics.get("used_reference", False))
    ssim = _finite_or_none(metrics.get("ssim"))
    sam = _finite_or_none(metrics.get("sam"))
    cov = _finite_or_none(metrics.get("ref_coverage"))

    # --- spatial fidelity ------------------------------------------------- #
    if not used_ref:
        add("spatial_fidelity", NOT_EVALUATED,
            "no high-resolution reference supplied; full-reference metrics not computed")
    else:
        missing = [k for k in ("psnr", "ssim") if _finite_or_none(
            metrics.get(k), allow_pos_inf=(k == "psnr")) is None]
        if missing:
            for key in missing:
                add("spatial_fidelity", FAIL,
                    f"mandatory reference metric missing or non-finite: {key}")
        elif ssim is not None and ssim < th["ssim_soft"]:
            add("spatial_fidelity", CAUTION,
                f"ssim below soft threshold ({ssim:.3f})", ssim, th["ssim_soft"])
        else:
            add("spatial_fidelity", PASS,
                f"ssim {ssim:.3f} at or above the soft threshold", ssim, th["ssim_soft"])

    # --- spectral fidelity ------------------------------------------------ #
    if not used_ref:
        add("spectral_fidelity", NOT_EVALUATED,
            "no high-resolution reference supplied; spectral agreement not computed")
    elif _finite_or_none(metrics.get("sam")) is None:
        add("spectral_fidelity", FAIL,
            "mandatory reference metric missing or non-finite: sam")
    elif sam is not None and sam > th["sam_soft"]:
        add("spectral_fidelity", CAUTION,
            f"sam above soft threshold ({sam:.3f} rad)", sam, th["sam_soft"])
    else:
        add("spectral_fidelity", PASS,
            f"sam {sam:.3f} rad within tolerance", sam, th["sam_soft"])

    # --- uncertainty quality ---------------------------------------------- #
    present = metrics.get("uncertainty_present")
    unc_cov = _finite_or_none(metrics.get("uncertainty_coverage"))
    if present is False:
        add("uncertainty_quality", FAIL,
            "uncertainty raster missing: the reconstruction was never quantified")
    else:
        calib = metrics.get("calibration_status")
        corr = _finite_or_none(metrics.get("error_correlation"))
        if unc_cov is not None and unc_cov < th["uncertainty_coverage_soft"]:
            add("uncertainty_quality", CAUTION,
                f"uncertainty covered only {unc_cov:.1%} of the grid",
                unc_cov, th["uncertainty_coverage_soft"])
        elif used_ref and corr is not None and corr < th["calib_corr_soft"]:
            # The only question that matters: does uncertainty predict error?
            add("uncertainty_quality", CAUTION,
                f"uncertainty calibration weak (corr={corr:.3f})",
                corr, th["calib_corr_soft"])
        elif used_ref and calib == "calibrated":
            add("uncertainty_quality", PASS,
                f"uncertainty tracks realized error (corr={corr:.3f})",
                corr, th["calib_corr_ok"])
        elif used_ref and corr is not None:
            add("uncertainty_quality", PASS,
                f"uncertainty/error correlation {corr:.3f} at or above the soft "
                "threshold", corr, th["calib_corr_soft"])
        elif used_ref:
            add("uncertainty_quality", NOT_EVALUATED,
                metrics.get("calibration_reason")
                or "uncertainty produced but calibration not established")
        elif present is True:
            add("uncertainty_quality", NOT_EVALUATED,
                metrics.get("calibration_reason")
                or "uncertainty produced but not calibrated (no reference)")
        else:
            add("uncertainty_quality", NOT_EVALUATED,
                "uncertainty contribution not declared by the caller")

    # --- reference coverage ----------------------------------------------- #
    if not used_ref:
        add("reference_coverage", NOT_EVALUATED,
            "no reference: this run reports observation consistency and uncertainty only")
    elif cov is None:
        add("reference_coverage", FAIL, "reference coverage could not be computed")
    elif cov < th["min_ref_coverage"]:
        add("reference_coverage", FAIL,
            f"reference coverage {cov:.3f} below minimum", cov, th["min_ref_coverage"])
    elif cov < th["ref_coverage_soft"]:
        add("reference_coverage", CAUTION,
            f"reference coverage {cov:.3f} below soft threshold",
            cov, th["ref_coverage_soft"])
    else:
        add("reference_coverage", PASS,
            f"reference covered {cov:.1%} of the evaluation grid",
            cov, th["ref_coverage_soft"])

    # --- valid pixel coverage --------------------------------------------- #
    vcov = _finite_or_none(metrics.get("valid_coverage"))
    if vcov is None:
        add("valid_coverage", NOT_EVALUATED, "valid-pixel coverage not reported")
    elif vcov < th["valid_coverage_soft"]:
        add("valid_coverage", CAUTION,
            f"only {vcov:.1%} of pixels carried usable observation",
            vcov, th["valid_coverage_soft"])
    else:
        add("valid_coverage", PASS, f"{vcov:.1%} of pixels carried usable observation",
            vcov, th["valid_coverage_soft"])

    checks.sort(key=lambda c: CHECK_ORDER.index(c["name"])
                if c["name"] in CHECK_ORDER else 99)

    if fails:
        return {"overall_status": FAIL, "score": 0.0, "reasons": fails,
                "cautions": cautions, "checks": checks, "thresholds_applied": th}

    # --- missing-evidence policy ------------------------------------------ #
    # No reference means no fidelity evidence and no way to score it. Return
    # CAUTION with the missing evidence named first; a partial composite (which
    # would be valid-pixel coverage alone) is exactly the kind of number that
    # makes an unverified reconstruction look validated.
    if not used_ref:
        cautions = [NO_REFERENCE_REASON, *cautions]
        return {"overall_status": CAUTION, "score": None,
                "score_note": NO_REFERENCE_SCORE_NOTE,
                "reasons": list(cautions), "cautions": cautions,
                "checks": checks, "thresholds_applied": th}

    parts: list[float] = []
    if ssim is not None:
        parts.append(float(np.clip(ssim, 0, 1)))
    if sam is not None:
        parts.append(float(np.clip(1.0 - sam / (np.pi / 4.0), 0, 1)))
    if vcov is not None:
        parts.append(float(np.clip(vcov, 0, 1)))
    score = round(float(np.mean(parts)), 3) if parts else 0.5

    return {"overall_status": CAUTION if cautions else PASS, "score": score,
            "reasons": cautions or ["all checks passed"], "cautions": cautions,
            "checks": checks, "thresholds_applied": th}


def decide_overall_status(geometric: dict, metrics: dict,
                          thresholds: dict | None = None) -> dict:
    """Backwards-compatible alias for :func:`quality_gate`."""
    return quality_gate(geometric, metrics, thresholds)


def classify_failure_modes(metrics: dict, checks: list[dict],
                           *, context: dict | None = None) -> list[dict]:
    """Explain *why* a result is weak, with what the system did and what to do.

    A gate verdict without a diagnosis is not actionable. Each entry names a
    plausible failure mode, the symptom that triggered it, the concrete cause,
    the system's own behaviour, and the next step an operator should take.
    This is deliberately evidence-linked: a mode is only reported when the
    metric that supports it is actually present and out of bounds.
    """
    context = context or {}
    th = DEFAULT_THRESHOLDS
    findings: list[dict] = []

    def add(mode_id, severity, symptom, cause, action):
        findings.append({"mode": mode_id, "severity": severity, "symptom": symptom,
                         "cause": cause,
                         "system_behaviour": "output produced but flagged, not hidden",
                         "action": action})

    vcov = _finite_or_none(metrics.get("valid_coverage"))
    obs = _finite_or_none(metrics.get("observation_rmse"))
    cov = _finite_or_none(metrics.get("ref_coverage"))
    sam = _finite_or_none(metrics.get("sam"))
    ssim = _finite_or_none(metrics.get("ssim"))
    corr = _finite_or_none(metrics.get("error_correlation"))
    unc_p95 = _finite_or_none(metrics.get("uncertainty_p95"))
    kind = metrics.get("uncertainty_kind")

    if vcov is not None and vcov < th["valid_coverage_soft"]:
        add("insufficient_valid_observation", "high",
            f"only {vcov:.1%} of the grid carried usable observation",
            "cloud, shadow or nodata masked most of the scene",
            "choose a clearer acquisition window or a different AOI")
    if obs is not None and obs > th["observation_rmse_hard"]:
        add("observation_inconsistency", "high",
            f"scale-back rmse {obs:.4f} exceeds the hard threshold",
            "the reconstruction disagrees with the original 10 m measurement it must be consistent with",
            "discard the output; re-run with a different model or revisit")
    if metrics.get("used_reference") and cov is not None and cov < th["ref_coverage_soft"]:
        add("weak_reference", "medium",
            f"the reference covered only {cov:.1%} of the evaluation grid",
            "the high-resolution reference does not fully overlap the SR footprint",
            "treat full-reference metrics as indicative; extend the reference footprint")
    if sam is not None and sam > th["sam_soft"]:
        add("spectral_distortion", "medium",
            f"spectral angle {sam:.3f} rad above tolerance",
            "generated detail does not preserve spectral ratios",
            "prefer the published baseline or retrain with a spectral-angle penalty")
    if ssim is not None and ssim < th["ssim_soft"]:
        add("fine_texture_mismatch", "medium",
            f"structural similarity {ssim:.3f} below tolerance",
            "fine texture was not reproduced consistently with the reference",
            "inspect the residual and uncertainty map before using the texture")
    if kind == "stochastic_sampling_std" and corr is not None \
            and corr < th["calib_corr_soft"]:
        add("uncertainty_not_calibrated", "medium",
            f"uncertainty/error correlation {corr:.3f} is weak",
            "the model's own uncertainty does not predict where it is wrong",
            "do not use the uncertainty map as a reliability mask on this scene")
    if kind == "auxiliary_gradient_indicator":
        add("uncertainty_not_probabilistic", "low",
            "the uncertainty raster is an edge-energy indicator",
            "the selected model has no stochastic sampler",
            "use opensr_ldsrs2 when a probabilistic uncertainty map is required")
    # The threshold is in reflectance standard-deviation units, so it only means
    # anything for a probabilistic map. An auxiliary gradient-energy indicator is
    # normalised to [0, 1] by construction and would trip this on every textured
    # scene, reporting "large uncertainty" about a quantity that is not one.
    if kind == "stochastic_sampling_std" and unc_p95 is not None and unc_p95 > 0.1:
        add("high_uncertainty", "medium",
            f"95th-percentile uncertainty {unc_p95:.4f} is large",
            "large parts of the reconstruction are weakly constrained by the input",
            "report the uncertainty alongside the product, not a point estimate")

    excluded = context.get("frames_excluded")
    if excluded:
        add("temporal_mismatch", "medium",
            f"{excluded} candidate revisit(s) failed the scene-change safeguard",
            "the surface changed between acquisitions, so those frames cannot be fused",
            "review the excluded frames; if the change is real, process each date separately")
    if not metrics.get("used_reference"):
        add("no_reference_available", "low",
            "no high-resolution reference was supplied",
            "operational AOIs rarely have paired high-resolution truth",
            "treat this run as a no-reference demonstration: consistency and "
            "uncertainty are reported, accuracy is not claimed")
    return findings
