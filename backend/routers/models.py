"""Model registry endpoints: approved models and their real runtime capability.

``GET /v1/models/status`` exists so the console never has to guess whether the
real super-resolution model can run. It answers with the actual probe result
(torch present? CUDA present? checkpoint staged and hash-verified? vendored
package importable?) and, when the answer is no, the specific reason. A UI that
shows "LDSR-S2: READY" is then showing a fact rather than an assumption.

Why these two routes are unauthenticated
----------------------------------------
Every other route in this service is project-scoped, and the model registry is
not: it is a static list of approved checkpoints plus their licences, and the
probe is a property of the host rather than of anybody's data. The problem
statement's demo must be reachable without inventing an operator identity, and a
reviewer has to be able to see *which* model would run and under which licence
before deciding whether to trust a result. Keeping this public is what makes
"the console never claims a capability it cannot show" true for an anonymous
visitor. Nothing project-scoped becomes reachable by it: jobs, artifacts,
validations and reports all keep their authentication and their ownership checks.

Because it is public, the failure reason is sanitised — an absolute local path
must not leak through an error string.
"""

from __future__ import annotations

import re

from fastapi import APIRouter

from backend import db
from backend.schemas import ModelOut

router = APIRouter(prefix="/v1/models", tags=["models"])

# Absolute POSIX and Windows paths, e.g. /srv/sentry/data/... or E:\SENTRY\data\...
_ABS_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s'\"]*[\\/][^\s'\"]*")


def _public_reason(reason: str | None) -> str | None:
    """Strip filesystem paths from a probe reason before serving it publicly."""
    if not reason:
        return reason
    return _ABS_PATH.sub("<path>", reason)


@router.get("", response_model=list[ModelOut])
async def list_models() -> list[ModelOut]:
    """List the approved model registry, enriched with worker capability cards.

    The database row is authoritative for identity/version/checksum; the worker
    registry supplies the executable capability description (learned,
    deterministic, uncertainty kind, optional dependency). Where they disagree
    the database wins, because that is what a validation report stamps.

    Degrades honestly: with no database configured the worker registry is still
    served, so a reviewer can see the approved models and their licences even
    when the control plane has no storage behind it.
    """
    from worker.registry import MODEL_REGISTRY

    rows = []
    try:
        rows = db.query(
            """
            select id, name, version, framework, model_card
            from model_versions order by name
            """
        ) or []
    except Exception:  # noqa: BLE001 - no DB configured: fall back to the registry
        rows = []

    if not rows:
        # Synthetic ids are namespaced so a caller can tell at a glance that these
        # did not come from the database, rather than mistaking them for rows.
        return [
            ModelOut(
                id=f"registry:{name}",
                name=name,
                version=card.get("version") or "in-repo",
                framework=card.get("framework"),
                model_card={**card, "source": "worker registry (no model_versions row)"},
            )
            for name, card in MODEL_REGISTRY.items()
        ]

    out: list[ModelOut] = []
    for row in rows:
        card = dict(row.get("model_card") or {})
        local = MODEL_REGISTRY.get(row["name"]) or {}
        for key, value in local.items():
            card.setdefault(key, value)
        out.append(ModelOut(**{**row, "model_card": card}))
    return out


@router.get("/status")
async def model_status() -> dict:
    """Runtime capability probe for the real super-resolution path.

    Imported lazily: the API process must stay importable without torch.
    """
    from worker.registry import MODEL_REGISTRY

    try:
        from worker import opensr
    except ImportError as exc:
        return {"ready": False, "reason": f"opensr backend unavailable: {exc}",
                "registry": {n: {"status": c.get("status")} for n, c in MODEL_REGISTRY.items()}}

    status = opensr.model_status()
    if status.get("reason"):
        status["reason"] = _public_reason(status["reason"])
    status["registry"] = {
        name: {
            "status": card.get("status"),
            "learned": card.get("learned"),
            "deterministic": card.get("deterministic"),
            "visual_only": card.get("visual_only"),
            "uncertainty_kind": card.get("uncertainty_kind"),
            "requires": card.get("requires"),
        }
        for name, card in MODEL_REGISTRY.items()
    }
    return status
