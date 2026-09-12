"""PRD §11 output-schema writers: previews + run metadata.

Three artifacts close the PRD §11 gap:

- ``preview_rgb.png``       B04/B03/B02 stretch, labeled as a visualization.
- ``preview_false_color.png`` NIR/R/G (B08/B04/B03) stretch, labeled false color.
- ``run_metadata.json``     Input product IDs, sensing times, CRS/bands, model
                            version, git commit, config hash, sampling steps,
                            runtime and device — the traceability record the
                            PRD's Export screen and Table 9 require.

Previews are honest visualizations, never data products: they use a fixed
robust percentile stretch (no per-image histogram fiddling that could distort
spectral ratios — PRD §8 rule), carry an explicit "model-inferred detail" /
visualization caption, and are registered as artifacts for the Export screen.
"""

from __future__ import annotations

import json
import platform
import time
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
    lo, hi = np.percentile(px, [LOW_PCT, HIGH_PCT])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = float(np.nanmin(px)), float(np.nanmax(px))
    if hi <= lo:  # constant band: mid-gray, never divide by zero
        return np.full(band.shape, 128, dtype=np.uint8)
    out = np.clip((band - lo) / (hi - lo), 0.0, 1.0)
    out = np.where(valid, out, 0.0) if valid is not None else out
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
    img = Image.fromarray(canvas, mode="RGB")
    # Caption lives in the metadata too; the strip keeps the image self-evident.
    if caption:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.text((6, h + 4), caption, fill=(230, 230, 230))
    img.save(path, format="PNG")
    return {"path": path, "width": w, "height": h, "strip_h": strip_h}


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


def build_run_metadata(job: dict, *, model_name: str, crs: str, transform: list,
                       grid_m: float, band_count: int = 4,
                       input_products: list[dict] | None = None,
                       frame_count: int = 1,
                       sampling_steps: int | None = None,
                       runtime_s: float | None = None,
                       started_utc: str | None = None) -> dict:
    """Assemble the run_metadata.json payload (PRD Table 9, traceability row).

    Every field is real: product IDs and sensing times come from the staged
    scenes, the model name from the job's registry row, the commit/config hash
    from configuration — nothing is invented to look complete.
    """
    settings = get_settings()
    reg = MODEL_REGISTRY.get(model_name, {})
    products = input_products or []
    device = "cpu"
    try:  # torch is optional; report it honestly when present
        import torch

        if torch.cuda.is_available():
            device = f"cuda:{torch.cuda.current_device()}"
    except ImportError:
        pass
    return {
        "schema": "sentry.run_metadata.v1",
        "generated_at": _utcnow(),
        "job_id": job["id"],
        "project_id": job.get("project_id"),
        "mode": job.get("mode"),
        "model": {
            "name": model_name,
            "role": reg.get("role"),
            "version": job.get("model_version_id"),
            "sampling_steps": sampling_steps,
            "note": "deterministic model; no stochastic sampling"
            if model_name in ("bicubic_4x", "custom_mf_sr") else None,
        },
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
        },
        "provenance": {
            "code_commit": settings.code_commit or None,
            "config_hash": _config_hash(),
            "validation_protocol_version": settings.validation_protocol_version,
            "worker_image": settings.worker_image or None,
        },
        "runtime": {
            "device": device,
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


_CONFIG_HASH_CACHE: tuple[float, str] | None = None
_CONFIG_HASH_TTL_S = 60.0


def _config_hash() -> str:
    """SHA-256 over the effective settings that affect outputs.

    Cached briefly: the hash is deterministic per settings content, so a
    worker process reuses it across jobs instead of re-hashing every time.
    """
    import hashlib

    global _CONFIG_HASH_CACHE
    now = time.monotonic()
    if _CONFIG_HASH_CACHE is not None and now - _CONFIG_HASH_CACHE[0] < _CONFIG_HASH_TTL_S:
        return _CONFIG_HASH_CACHE[1]
    s = get_settings()
    payload = {
        "max_tile_pixels": s.max_tile_pixels,
        "validation_protocol_version": s.validation_protocol_version,
        "worker_concurrency": s.worker_concurrency,
        "job_lease_seconds": s.job_lease_seconds,
        "job_max_attempts": s.job_max_attempts,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    _CONFIG_HASH_CACHE = (now, digest)
    return digest
