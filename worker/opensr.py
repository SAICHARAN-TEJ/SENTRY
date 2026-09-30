"""OpenSR LDSR-S2 backend probe (fail-closed stub).

Real inference requires torch + the vendored opensr-model package + the
pinned checkpoint (see SOURCES.md). This module never raises at import time;
it reports capability via model_status() so the API can stay importable
without heavy deps.
"""

from __future__ import annotations

from pathlib import Path

from backend.config import get_settings


def model_status() -> dict:
    """Probe torch / checkpoint / package and report readiness."""
    settings = get_settings()
    try:
        import torch  # noqa: F401
        torch_ok = True
        cuda = bool(getattr(__import__("torch"), "cuda", None) and __import__("torch").cuda.is_available())
    except ImportError as exc:
        return {"ready": False, "reason": f"torch not installed: {exc}", "cuda": False}
    ckpt = settings.opensr_checkpoint or "data/opensr/opensr-ldsrs2_v1_0_0.ckpt"
    exists = Path(ckpt).exists()
    if not exists:
        return {"ready": False, "reason": f"checkpoint not staged: {ckpt}", "cuda": cuda}
    try:
        import importlib.util as _ilu
        pkg = _ilu.find_spec("opensr_model") or _ilu.find_spec("opensr_models")
        if pkg is None:
            return {"ready": False, "reason": "opensr-model package not installed", "cuda": cuda}
    except Exception as exc:
        return {"ready": False, "reason": f"opensr probe failed: {exc}", "cuda": cuda}
    return {"ready": True, "reason": None, "cuda": cuda, "checkpoint": ckpt}
