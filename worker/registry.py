"""Worker model registry: keys, execution roles, visual-only guards (PRD 8.2)."""

from __future__ import annotations

MODEL_REGISTRY: dict[str, dict] = {
    "bicubic_4x": {"role": "reference interpolation baseline", "visual_only": False,
                   "display_name": "Bicubic 4x", "status": "ready", "learned": False,
                   "deterministic": True, "bands": ["B02", "B03", "B04", "B08"],
                   "framework": "numpy/skimage", "license": "in-repo",
                   "uncertainty_kind": None, "requires": None},
    "opensr_ldsrs2": {"role": "primary published SR baseline", "visual_only": False,
                      "display_name": "OpenSR LDSR-S2", "status": "needs_weights",
                      "learned": True, "deterministic": False,
                      "bands": ["B02", "B03", "B04", "B08"],
                      "framework": "pytorch/diffusion", "license": "see SOURCES.md",
                      "uncertainty_kind": "stochastic_sampling_std", "requires": "torch"},
    "custom_mf_sr": {"role": "deterministic multi-frame fusion heuristic (not a learned network)",
                     "visual_only": False, "display_name": "Custom MF SR",
                     "status": "ready", "learned": False, "deterministic": True,
                     "bands": ["B02", "B03", "B04", "B08"], "framework": "numpy/skimage",
                     "license": "in-repo", "uncertainty_kind": "auxiliary_gradient_indicator",
                     "requires": None},
    "realesrgan_optional": {"role": "visual-only auxiliary", "visual_only": True,
                            "display_name": "RealESRGAN (visual only)", "status": "blocked",
                            "learned": True, "deterministic": False, "bands": ["RGB"],
                            "framework": "pytorch", "license": "see SOURCES.md",
                            "uncertainty_kind": None, "requires": "torch"},
}
