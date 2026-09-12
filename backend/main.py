"""FastAPI application factory: routers, error handling, health."""

from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import db
from backend.config import get_settings
from backend.errors import ApiError
from backend.schemas import HealthOut

log = logging.getLogger("sentry")


def create_app() -> FastAPI:
    """Build the Sentry API application."""
    app = FastAPI(title="SIH26142 Sentry API", version="0.1.0")
    settings = get_settings()
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "X-Dev-User"],
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.http_status,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        """Keep implementation details and credentials out of API responses."""
        log.exception("unhandled API exception", exc_info=exc)
        return JSONResponse(
            {"error": {"code": "INTERNAL", "message": "internal server error"}},
            status_code=500,
        )

    @app.get("/v1/health", response_model=HealthOut)
    async def health() -> HealthOut:
        db_ok = False
        try:
            db.query("select 1 as ok")
            db_ok = True
        except Exception:  # noqa: BLE001 - health must never raise
            db_ok = False
        storage_ok = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(settings.storage_url)
                storage_ok = resp.status_code < 500
        except Exception:  # noqa: BLE001
            storage_ok = False
        return HealthOut(status="ok", db=db_ok, storage=storage_ok,
                         protocol_version=settings.validation_protocol_version)

    from backend.routers import (aois, artifacts, jobs, models,  # noqa: PLC0415
                                 projects, reports, scenes, validations)

    app.include_router(projects.router)
    app.include_router(aois.router)
    app.include_router(scenes.router)
    app.include_router(jobs.router)
    app.include_router(validations.router)
    app.include_router(reports.router)
    app.include_router(artifacts.router)
    app.include_router(models.router)
    return app


app = create_app()
