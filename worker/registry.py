"""Worker model registry: keys, execution roles, visual-only guards (PRD 8.2)."""

from __future__ import annotations

MODEL_REGISTRY: dict[str, dict] = {
    "bicubic_4x": {"role": "reference interpolation baseline", "visual_only": False},
    "opensr_ldsrs2": {"role": "primary published SR baseline", "visual_only": False},
    "custom_mf_sr": {"role": "team multi-frame model", "visual_only": False},
    "realesrgan_optional": {"role": "visual-only auxiliary", "visual_only": True},
}
