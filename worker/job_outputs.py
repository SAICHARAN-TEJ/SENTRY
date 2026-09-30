"""Output-schema writers: previews + run metadata.

Preview artifacts (all PNG, all explicit visualizations):

- ``preview_rgb.png``           B04/B03/B02 stretch of the 2.5 m output.
- ``preview_false_color.png``   NIR/R/G (B08/B04/B03) of the 2.5 m output.
- ``preview_observation.png``   B04/B03/B02 of the **10 m observed** input, so
                                the comparison view shows observed next to
                                model-inferred instead of leaving one side empty.
- ``preview_uncertainty.png``   the uncertainty raster on a single-hue ramp,
                                labelled with what the quantity actually is.
- ``preview_residual.png``      scale-back residual magnitude map.
- ``run_metadata.json``         traceability record: input product IDs, sensing
                                times, CRS/bands, model card, checkpoint hash,
                                commit, config hash, sampling steps, runtime,
                                device, uncertainty semantics, frame selection.

Previews are honest visualizations, never data products: they use a fixed
robust percentile stretch (no per-image histogram fiddling that could distort
spectral ratios — PRD §8 rule), carry an explicit caption, and are registered
as artifacts for the Export screen. No GeoTIFF is ever presented as a picture
and no picture is ever presented as data.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.config import get_settings
from worker.registry import MODEL_REGISTRY

BANDS = ["B02", "B03", "B04", "B08"]
LOW_PCT, HIGH_PCT = 2.0, 98.0


def _stretch(band: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Fixed robust percentile stretch -> uint8 [0,255].

    The percentiles are computed over valid pixels only, then applied to the
    whole band (invalid pixels go to 0). The kernel is fixed by configuration,
    not chosen per image, so it cannot silently distort spectral structure.
    """
    px = band[valid] if valid is not None and valid.any() else band.ravel()
    if px.size == 0 or not np.isfinite(px).any():
        # Nothing finite to stretch (empty or all-NaN band): mid-gray, and no
        # invalid-cast warnings from NaN -> uint8 conversion.
        return np.full(band.shape, 128, dtype=np.uint8)
    with np.errstate(invalid="ignore"):
        lo, hi = np.percentile(px, [LOW_PCT, HIGH_PCT])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        finite = px[np.isfinite(px)]
        lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:  # constant band: mid-gray, never divide by zero
        return np.full(band.shape, 128, dtype=np.uint8)
    out = np.clip((band - lo) / (hi - lo), 0.0, 1.0)
    out = np.where(valid, out, 0.0) if valid is not None else out
    out = np.where(np.isfinite(out), out, 0.0)
    return (out * 255.0 + 0.5).astype(np.uint8)


def _composite_png(path: Path, channels: list[np.ndarray], valid: np.ndarray,
                   caption: str) -> dict:
    """Stack 3 stretched channels into an RGB PNG with a caption strip."""
    from PIL import Image

    h, w = channels[0].shape
    rgb = np.stack(channels, axis=-1)  # (h, w, 3) uint8
    strip_h = 18
    canvas = np.zeros((h + strip_h, w, 3), dtype=np.uint8)
    canvas[:h] = rgb
    img = Image.fromarray(canvas)
    # Caption lives in the metadata too; the strip keeps the image self-evident.
    if caption:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.text((6, h + 4), caption, fill=(230, 230, 230))
    img.save(path, format="PNG", optimize=True)
    return {"path": path, "width": w, "height": h, "strip_h": strip_h}


def _ramp_png(path: Path, values: np.ndarray, valid: np.ndarray, caption: str,
              low_rgb: tuple, high_rgb: tuple,
              percentile: tuple[float, float] = (2.0, 98.0)) -> dict:
    """Render a single-band field through a two-colour ramp with a caption strip.

    Fixed percentile stretch over valid pixels only, so the render is a stable
    visualization rather than a per-image autoscaled picture. Returns the same
    shape of result as :func:`_composite_png`.
    """
    from PIL import Image, ImageDraw

    px = values[valid] if valid is not None and valid.any() else values.ravel()
    if px.size == 0 or not np.isfinite(px).any():
        norm = np.zeros_like(values, dtype=np.float32)
    else:
        with np.errstate(invalid="ignore"):
            lo, hi = np.percentile(px, list(percentile))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            finite = px[np.isfinite(px)]
            lo, hi = float(finite.min()), float(finite.max())
        if hi <= lo:
            norm = np.zeros_like(values, dtype=np.float32)
        else:
            norm = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
            norm = np.where(np.isfinite(norm), norm, 0.0)
    if valid is not None:
        norm = np.where(valid, norm, 0.0)
    lo_c = np.array(low_rgb, dtype=np.float32)
    hi_c = np.array(high_rgb, dtype=np.float32)
    rgb = (lo_c[None, None, :] + norm[..., None] * (hi_c - lo_c)[None, None, :])
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    h, w = values.shape
    strip_h = 18
    canvas = np.zeros((h + strip_h, w, 3), dtype=np.uint8)
    canvas[:h] = rgb
    img = Image.fromarray(canvas)
    if caption:
        ImageDraw.Draw(img).text((6, h + 4), caption, fill=(230, 230, 230))
    img.save(path, format="PNG", optimize=True)
    return {"path": path, "width": w, "height": h, "strip_h": strip_h,
            "stretch_percentiles": list(percentile)}


def write_observation_preview(observation: np.ndarray, valid: np.ndarray,
                              out_dir: Path,
                              label: str = "observed Sentinel-2 L2A, 10 m"
                              ) -> dict:
    """True-colour preview of the **observed** 10 m input.

    This is the left-hand side of the comparison view. It is observed data, not
    a reconstruction, and the caption says so.
    """
    if observation.ndim != 3 or observation.shape[0] != 4:
        raise ValueError("expected (4, H, W) observation")
    out_dir.mkdir(parents=True, exist_ok=True)
    b02, b03, b04, _b08 = (observation[i] for i in range(4))
    return _composite_png(out_dir / "preview_observation.png",
                          [_stretch(b04, valid), _stretch(b03, valid),
                           _stretch(b02, valid)],
                          valid, f"True color RGB | {label} (visualization)")


def write_uncertainty_preview(unc: np.ndarray, valid: np.ndarray, out_dir: Path,
                              caption: str) -> dict:
    """Single-hue render of the uncertainty raster (dark -> warm).

    ``caption`` must state what the quantity is; the caller passes wording taken
    from the run metadata so the picture cannot overclaim what it shows.
    """
    band = unc[0] if unc.ndim == 3 else unc
    out_dir.mkdir(parents=True, exist_ok=True)
    return _ramp_png(out_dir / "preview_uncertainty.png", band.astype(np.float32),
                     valid, caption, low_rgb=(10, 14, 26), high_rgb=(250, 205, 90))


def write_residual_preview(sr: np.ndarray, observation: np.ndarray, out_dir: Path,
                           valid: np.ndarray | None = None,
                           caption: str | None = None) -> dict:
    """Scale-back residual magnitude map: observed minus the degraded SR output.

    Uses the same documented degradation operator as the validation engine
    (anti-aliased resize), so the picture and the reported scale-back RMSE are
    measuring the same thing.
    """
    from skimage.transform import resize

    if sr.ndim != 3 or observation.ndim != 3:
        raise ValueError("expected (4, H, W) arrays")
    down = np.stack(
        [resize(sr[i], observation.shape[1:], anti_aliasing=True, preserve_range=True)
         for i in range(sr.shape[0])], axis=0).astype(np.float32)
    residual = np.abs(down - observation).mean(axis=0)
    grid = np.ones(residual.shape, dtype=bool) if valid is None else valid
    out_dir.mkdir(parents=True, exist_ok=True)
    text = caption or ("scale-back residual |SR_2.5m degraded to 10 m - observed| "
                       "(visualization)")
    return _ramp_png(out_dir / "preview_residual.png", residual, grid, text,
                     low_rgb=(8, 10, 16), high_rgb=(244, 63, 94))


def write_previews(sr: np.ndarray, valid: np.ndarray, out_dir: Path,
                   *, false_color_dir: Path | None = None,
                   label: str = "model-inferred detail (visualization)") -> dict:
    """Write preview_rgb.png and preview_false_color.png from a (4, H, W) SR.

    ``sr`` is [0,1] reflectance in B02/B03/B04/B08 order; ``valid`` is the
    (H, W) valid-pixel mask (False pixels render black). ``false_color_dir``
    defaults to ``out_dir``; callers may split the two artifacts across their
    own artifact-type directories. Returns a dict keyed by filename with
    pixel dimensions for artifact registration.
    """
    if sr.ndim != 3 or sr.shape[0] != 4:
        raise ValueError("expected (4, H, W) reflectance array")
    out_dir.mkdir(parents=True, exist_ok=True)
    fc_dir = false_color_dir if false_color_dir is not None else out_dir
    fc_dir.mkdir(parents=True, exist_ok=True)
    b02, b03, b04, b08 = (sr[i] for i in range(4))
    results: dict = {}
    results["preview_rgb.png"] = _composite_png(
        out_dir / "preview_rgb.png",
        [_stretch(b04, valid), _stretch(b03, valid), _stretch(b02, valid)],
        valid, f"True color RGB | {label}")
    results["preview_false_color.png"] = _composite_png(
        fc_dir / "preview_false_color.png",
        [_stretch(b08, valid), _stretch(b04, valid), _stretch(b03, valid)],
        valid, f"False color NIR/R/G | {label}")
    return results


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _device_label(model_metadata: dict | None) -> str:
    """Report the device the model actually ran on, never an assumed one."""
    if model_metadata and model_metadata.get("device"):
        device = str(model_metadata["device"])
        name = model_metadata.get("cuda_device_name")
        return f"{device} ({name})" if name else device
    try:
        import torch

        if torch.cuda.is_available():
            return f"cuda:{torch.cuda.current_device()} ({torch.cuda.get_device_name(0)})"
    except Exception:  # noqa: BLE001 - driver failures mean "no usable CUDA"
        pass
    return "cpu"


def build_run_metadata(job: dict, *, model_name: str, crs: str, transform: list,
                       grid_m: float, band_count: int = 4,
                       input_products: list[dict] | None = None,
                       frame_count: int = 1,
                       sampling_steps: int | None = None,
                       runtime_s: float | None = None,
                       started_utc: str | None = None,
                       model_metadata: dict | None = None,
                       uncertainty: dict | None = None,
                       frame_selection: dict | None = None,
                       tile_pixels: int | None = None,
                       spatial_extent: dict | None = None) -> dict:
    """Assemble the run_metadata.json payload (PRD Table 9, traceability row).

    Every field is real: product IDs and sensing times come from the staged
    scenes, the model card and checkpoint hash from the registry/adapter, the
    commit/config hash from configuration — nothing is invented to look complete.
    """
    settings = get_settings()
    reg = MODEL_REGISTRY.get(model_name, {})
    products = input_products or []
    deterministic = model_name in ("bicubic_4x", "custom_mf_sr")
    return {
        "schema": "sentry.run_metadata.v1",
        "generated_at": _utcnow(),
        "job_id": job["id"],
        "project_id": job.get("project_id"),
        "mode": job.get("mode"),
        # Where this run's artifacts physically live (v2 addition, additive).
        "artifact_store": settings.artifact_store_mode,
        "model": {
            "name": model_name,
            "display_name": reg.get("display_name"),
            "role": reg.get("role") or reg.get("display_name"),
            "status": reg.get("status"),
            "learned": bool(reg.get("learned")),
            "deterministic": bool(reg.get("deterministic", deterministic)),
            "band_order": reg.get("bands"),
            "version": job.get("model_version_id"),
            "version_id": job.get("model_version_id"),
            "sampling_steps": sampling_steps,
            "checkpoint": (model_metadata or {}).get("checkpoint"),
            "framework": (model_metadata or {}).get("framework") or reg.get("framework"),
            "license": (model_metadata or {}).get("license") or reg.get("license"),
            "parameters": (model_metadata or {}).get("parameters"),
            "note": reg.get("note")
            or ("deterministic model; no stochastic sampling"
                if deterministic else None),
        },
        "uncertainty": uncertainty,
        "frame_selection": frame_selection,
        "inputs": {
            "frame_count": frame_count,
            "products": [
                {
                    "provider_product_id": p.get("provider_product_id"),
                    "sensing_time": p.get("sensing_time"),
                    "tile_id": p.get("tile_id"),
                    "processing_baseline": p.get("processing_baseline"),
                }
                for p in products
            ],
        },
        "grid": {
            "bands": BANDS[:band_count] if band_count else None,
            "band_count": band_count,
            "grid_m": grid_m,
            "crs": crs,
            "transform": transform,
            "tile_pixels": tile_pixels,
        },
        # What extent of the input was actually processed: the AOI the job was
        # submitted for and the pixel window read from each scene. Null when the
        # job named no AOI, so a whole-scene run never reads as an AOI clip.
        "spatial_extent": spatial_extent,
        "provenance": {
            "code_commit": settings.code_commit or None,
            "config_hash": _config_hash(),
            "validation_protocol_version": settings.validation_protocol_version,
            "worker_image": settings.worker_image or None,
        },
        "runtime": {
            "device": _device_label(model_metadata),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "runtime_s": round(runtime_s, 3) if runtime_s is not None else None,
            "started_utc": started_utc,
            "finished_utc": _utcnow(),
        },
    }


def write_run_metadata(path: Path, metadata: dict) -> Path:
    """Serialize run_metadata.json (stable key order, human-readable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, default=str))
    return path


def _config_hash() -> str:
    """SHA-256 over the effective settings that affect outputs.

    Computed fresh every call (hashing a dozen keys costs microseconds): a
    TTL cache here would stamp a stale hash whenever settings change
    mid-process, which is exactly what provenance must never do.
    """
    import hashlib

    s = get_settings()
    payload = {
        "max_tile_pixels": s.max_tile_pixels,
        "validation_protocol_version": s.validation_protocol_version,
        "worker_concurrency": s.worker_concurrency,
        "job_lease_seconds": s.job_lease_seconds,
        "job_max_attempts": s.job_max_attempts,
        # Every value below changes the produced pixels, so it must move the hash.
        "opensr_checkpoint": s.opensr_checkpoint,
        "opensr_checkpoint_sha256": s.opensr_checkpoint_sha256,
        "opensr_device": s.opensr_device,
        "opensr_sampling_steps": s.opensr_sampling_steps,
        "opensr_window": s.opensr_window,
        "opensr_overlap": s.opensr_overlap,
        "uncertainty_samples": s.uncertainty_samples,
        "uncertainty_sampling_steps": s.uncertainty_sampling_steps,
        "uncertainty_enabled": s.uncertainty_enabled,
        "frame_change_risk_max": s.frame_change_risk_max,
        "frame_max_selected": s.frame_max_selected,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
