"""Model registry endpoints: list approved models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend import db
from backend.auth import get_current_user
from backend.schemas import ModelOut

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
async def list_models(user: dict = Depends(get_current_user)) -> list[ModelOut]:
    """List the approved model registry (model cards included)."""
    rows = db.query(
        """
        select id, name, version, framework, model_card
        from model_versions order by name
        """
    )
    return [ModelOut(**r) for r in rows]  # type: ignore[misc]
