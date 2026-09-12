"""SR baselines: bicubic, OpenSR hook, custom multi-frame model, uncertainty proxy."""

from __future__ import annotations

import numpy as np
from skimage.filters import sobel
from skimage.transform import resize

from backend.errors import ApiError, MODEL_UNAVAILABLE

REPO_NOTE = "github.com/ESAOpenSR/opensr-model"


def run_bicubic(tile_pixels: np.ndarray, scale: int = 4) -> np.ndarray:
    """Deterministic interpolation baseline: (B, h, w) -> (B, h*scale, w*scale)."""
    if tile_pixels.ndim != 3:
        raise ValueError("expected (B, h, w)")
    b, h, w = tile_pixels.shape
    up = np.zeros((b, h * scale, w * scale), dtype=np.float32)
    for i in range(b):
        up[i] = resize(tile_pixels[i], (h * scale, w * scale),
                       anti_aliasing=True, preserve_range=True)
    return up.astype(np.float32)


def run_opensr(tile_pixels: np.ndarray, checkpoint: str | None = None) -> np.ndarray:
    """ESA LDSR-S2 / OpenSR baseline; requires the opensr package + checkpoint."""
    try:
        import opensr_models  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on optional env
        raise ApiError(
            MODEL_UNAVAILABLE,
            f"OpenSR/LDSR-S2 package not installed — see {REPO_NOTE}",
        ) from exc
    raise ApiError(MODEL_UNAVAILABLE,
                   f"OpenSR weights not staged (checkpoint={checkpoint}) — see {REPO_NOTE}")


def _gradient_energy(px: np.ndarray) -> float:
    """Mean Sobel magnitude across bands: sharpness score for frame selection."""
    mags = [np.mean(np.abs(sobel(px[i]))) for i in range(px.shape[0])]
    return float(np.mean(mags))


def run_custom_mf(frames: list[np.ndarray], scale: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic multi-frame reference model: sharp-frame selection + HF modulation.

    frames: list of (B, h, w) temporal observations of the same footprint.
    Returns ((B, h*scale, w*scale) sr, (1, h*scale, w*scale) uncertainty in [0,1]).
    """
    if not frames:
        raise ValueError("custom_mf_sr needs at least one frame")
    frames = [np.asarray(f, dtype=np.float32) for f in frames]
    if any(f.ndim != 3 or f.shape[0] != 4 for f in frames):
        raise ValueError("every temporal frame must have shape (4, h, w)")
    if any(f.shape != frames[0].shape for f in frames[1:]):
        raise ValueError("temporal frames must share one aligned shape")
    base = max(frames, key=_gradient_energy)

    sr = run_bicubic(base, scale)
    b, H, W = sr.shape

    # Temporal residual high-pass modulation (needs >1 frame to matter).
    # Accumulate the mean/variance online instead of materializing a list of
    # every upsampled band.  A 2048x2048 four-band tile is ~64 MiB; the old
    # list-based implementation needed ~200 MiB before model/output buffers.
    if len(frames) > 1:
        count = 0
        mean_plane = np.zeros((H, W), dtype=np.float32)
        m2_plane = np.zeros((H, W), dtype=np.float32)
        for frame in frames:
            up = run_bicubic(frame, scale)
            # Preserve the original model's scalar-over-all-bands behavior,
            # but release the full temporary frame before the next iteration.
            for band in range(b):
                count += 1
                plane = up[band]
                delta = plane - mean_plane
                mean_plane += delta / count
                m2_plane += delta * (plane - mean_plane)
            del up
        high = sr.mean(axis=0) - mean_plane
        temporal_var = m2_plane / max(count, 1)
        modulation = 1.0 + 0.5 * high * (1.0 / (1.0 + temporal_var + 1e-6))
        sr = sr * modulation[None, :, :]
        sr = np.clip(sr, 0.0, 1.0).astype(np.float32)

    unc = uncertainty_proxy(sr)
    return sr.astype(np.float32), unc


def uncertainty_proxy(sr: np.ndarray) -> np.ndarray:
    """Gradient-magnitude uncertainty proxy in [0, 1] (99th percentile normalization)."""
    if sr.ndim != 3:
        raise ValueError("expected (B, H, W)")
    mags = np.stack([np.abs(sobel(sr[i])) for i in range(sr.shape[0])], axis=0)
    agg = mags.mean(axis=0)
    p99 = np.percentile(agg, 99) if agg.size else 0.0
    if p99 <= 0:
        norm = np.zeros_like(agg)
    else:
        norm = np.clip(agg / p99, 0.0, 1.0)
    return norm.astype(np.float32)[None, :, :]  # (1, H, W)
