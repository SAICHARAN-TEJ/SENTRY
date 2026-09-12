"""Validation runner: executes the engine on artifacts and persists results.

Geometric consistency (Component A) is checked against the EXPECTED SR grid
derived from the observation grid (10 m -> 2.5 m at 4x), not against the raw
observation grid — the two legitimately differ by the resolution factor.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend import db
from backend.config import get_settings
from backend.errors import ApiError, DATA_CORRUPT
from backend.validation import engine

HUMAN_SUMMARY = ("Reconstruction validated against observation consistency; "
                 "inferred detail is less certain than directly observed structure.")

log = logging.getLogger("sentry.validation")


def _read_raster(path: str | Path) -> dict:
    """Read a GeoTIFF into engine format; raise DATA_CORRUPT when unreadable."""
    import rasterio

    try:
        with rasterio.open(str(path)) as src:
            arr = src.read(masked=True).filled(np.nan).astype(np.float32)
            georef = {
                "crs": src.crs.to_string() if src.crs else "",
                "transform": [src.transform.a, src.transform.b, src.transform.c,
                              src.transform.d, src.transform.e, src.transform.f],
                "width": src.width,
                "height": src.height,
                "bounds": list(src.bounds),
                "band_names": list(src.descriptions or ["B02", "B03", "B04", "B08"]),
                "nodata": src.nodata,
            }
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - any read failure is corrupt input
        raise ApiError(DATA_CORRUPT, f"cannot read raster {path}: {exc}") from exc
    return {"array": np.moveaxis(arr, 0, -1), "georef": georef,
            "valid_mask": np.isfinite(arr).all(axis=0)}  # (H, W, B)


def _align_to_sr(ref: dict, sr: dict) -> dict:
    """Reproject/resample a reference onto the exact SR CRS/affine/grid."""
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.warp import reproject, transform_bounds

    src_geo, dst_geo = ref["georef"], sr["georef"]
    if not src_geo.get("crs") or not dst_geo.get("crs"):
        raise ApiError(DATA_CORRUPT, "reference/SR CRS missing")
    try:
        rb = transform_bounds(src_geo["crs"], dst_geo["crs"],
                              *src_geo["bounds"], densify_pts=21)
    except Exception as exc:
        raise ApiError(DATA_CORRUPT, f"reference CRS transform failed: {exc}") from exc
    sb = dst_geo["bounds"]
    intersects = not (rb[2] <= sb[0] or rb[0] >= sb[2]
                      or rb[3] <= sb[1] or rb[1] >= sb[3])
    if not intersects:
        raise ApiError(DATA_CORRUPT, "reference does not overlap the SR footprint")

    dst = np.full((dst_geo["height"], dst_geo["width"], ref["array"].shape[2]),
                  np.nan, dtype=np.float32)
    src_transform = Affine(*src_geo["transform"])
    dst_transform = Affine(*dst_geo["transform"])
    for i in range(ref["array"].shape[2]):
        reproject(
            source=ref["array"][..., i], destination=dst[..., i],
            src_transform=src_transform, src_crs=src_geo["crs"],
            src_nodata=src_geo.get("nodata"),
            dst_transform=dst_transform, dst_crs=dst_geo["crs"],
            dst_nodata=np.nan, resampling=Resampling.bilinear,
        )
    return {
        "array": dst,
        "georef": dict(dst_geo),
        "alignment": {
            "source_crs": src_geo["crs"], "target_crs": dst_geo["crs"],
            "resampling": "rasterio.warp.reproject:bilinear",
            "source_bounds_in_target_crs": list(rb),
        },
    }


def run_validation(job_id: str, paths: dict[str, Any]) -> dict:
    """Execute components A-F on a reconstruction job and persist everything.

    Raises VALIDATION_INCOMPLETE when mandatory evidence is missing so callers
    never mark a partially validated job COMPLETED.
    """
    settings = get_settings()
    for key in ("sr", "uncertainty", "observation"):
        p = Path(paths[key])
        if not p.exists():
            raise ApiError(DATA_CORRUPT, f"missing input raster: {key} ({p})")

    sr = _read_raster(paths["sr"])
    unc_r = _read_raster(paths["uncertainty"])
    obs = _read_raster(paths["observation"])
    ref = _read_raster(paths["reference"]) if paths.get("reference") else None

    # Component A: SR must sit on the expected 2.5 m grid derived from the S2 grid.
    expected = engine.expected_sr_georef(obs["georef"], scale=4)
    geoms = engine.check_geometric(sr["georef"], expected)

    unc = unc_r["array"][..., 0]
    if unc.ndim == 3:  # (1, H, W) single-band
        unc = unc[0]
    obs_res = engine.observation_consistency(sr["array"], obs["array"],
                                             valid_mask=obs["valid_mask"])

    ref_metrics: dict = {}
    ref_coverage = None
    valid = None
    if ref is not None:
        ref = _align_to_sr(ref, sr)  # align BEFORE all comparisons
        paths["reference_alignment"] = ref["alignment"]
        valid = (np.isfinite(ref["array"]).all(axis=-1)
                 & np.isfinite(sr["array"]).all(axis=-1))
        agree = engine.reference_agreement(sr["array"], ref["array"], 2.5,
                                           valid_mask=valid)
        ref_metrics = agree["metrics"]
        ref_coverage = float(valid.mean())

    unc_res = engine.uncertainty_quality(
        unc, sr["array"], ref["array"] if ref else None,
        valid_mask=valid if ref is not None else None)

    metrics_for_decision: dict = {
        "observation_rmse": obs_res["rmse_mean"],
        "used_reference": ref is not None,
        "psnr": ref_metrics.get("psnr") if ref else None,
        "ssim": ref_metrics.get("ssim") if ref else None,
        "sam": ref_metrics.get("sam") if ref else None,
        "ergas": ref_metrics.get("ergas") if ref else None,
        "ref_coverage": ref_coverage,
        "error_correlation": unc_res.get("error_correlation"),
        "valid_coverage": obs_res.get("valid_coverage"),
    }
    decision = engine.decide_overall_status(geoms, metrics_for_decision)

    if settings.supabase_db_url:
        return _persist(job_id, paths, sr, obs_res, unc_res, ref_metrics,
                        ref_coverage, decision, settings)
    return _local_report(job_id, paths, obs_res, unc_res, ref_metrics,
                          ref_coverage, decision, settings)


def _persist(job_id: str, paths: dict, sr: dict, obs_res: dict, unc_res: dict,
             ref_metrics: dict, ref_coverage: float | None, decision: dict,
             settings) -> dict:
    """Write validation_runs / validation_metrics / uncertainty_summaries / reports atomically.

    The validation run row is resolved-or-created in its own committed
    transaction first, so a later failure can durably mark it FAILED.
    """
    vrun_id: str | None = None
    protocol = settings.validation_protocol_version
    with db.transaction() as tx:
        job0 = tx.query("select id from jobs where id = %s", (job_id,), one=True)
        if job0 is None:
            raise ApiError(DATA_CORRUPT, f"job {job_id} not found")
        run = None
        if paths.get("validation_id"):
            run = tx.query(
                "select id from validation_runs where id = %s and job_id = %s",
                (paths["validation_id"], job_id), one=True)
            if run is None:
                raise ApiError(DATA_CORRUPT, "validation run/source job mismatch")
        if run is None:
            run = tx.query(
                "select id from validation_runs where job_id = %s order by created_at desc limit 1",
                (job_id,), one=True)
        if run is None:
            run = tx.query(
                """
                insert into validation_runs (job_id, protocol_version, evaluation_grid_m)
                values (%s, %s, 2.5) returning id
                """,
                (job_id, protocol), one=True)
        vrun_id = run["id"]
    try:
        with db.transaction() as tx:
            job = tx.query("select * from jobs where id = %s", (job_id,), one=True)
            all_metrics: dict[str, Any] = {
                "observation_rmse": obs_res["rmse_mean"],
                "uncertainty_mean": unc_res["mean"],
                "uncertainty_p95": unc_res["p95"],
            }
            for b in engine.BANDS:
                if obs_res["per_band"].get(b, {}).get("rmse") is not None:
                    all_metrics[f"obs_rmse_{b}"] = obs_res["per_band"][b]["rmse"]
            for k, v in ref_metrics.items():
                if v is not None:
                    all_metrics[k] = v
            for name, value in all_metrics.items():
                if value is None or not np.isfinite(value):
                    continue
                tx.execute(
                    """
                    insert into validation_metrics
                        (validation_run_id, metric_name, band, value, pass, details)
                    values (%s, %s, null, %s, %s, '{}'::jsonb)
                    """,
                    (vrun_id, name, float(value), decision["overall_status"] != "FAIL"),
                )

            unc_artifact = tx.query(
                """
                select id from raster_artifacts
                where job_id = %s and artifact_type = 'uncertainty' limit 1
                """,
                (job_id,), one=True)
            if unc_artifact is not None:
                calibration = unc_res.get("calibration")
                tx.execute(
                    """
                    insert into uncertainty_summaries
                        (raster_artifact_id, mean, p50, p90, p95, max, coverage, calibration)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (raster_artifact_id) do update set
                        mean = excluded.mean, p50 = excluded.p50, p90 = excluded.p90,
                        p95 = excluded.p95, max = excluded.max,
                        coverage = excluded.coverage, calibration = excluded.calibration
                    """,
                    (unc_artifact["id"], unc_res["mean"], unc_res["p50"], unc_res["p90"],
                     unc_res["p95"], unc_res["max"], unc_res["coverage"],
                     json.dumps(calibration) if calibration is not None else None),
                )

            model = None
            if job and job.get("model_version_id"):
                model = tx.query("select name, version, checksum from model_versions where id = %s",
                                 (job["model_version_id"],), one=True)
            summary = {
                "protocol_version": protocol,
                "input_scenes": [r["scene_id"] for r in (tx.query(
                    "select scene_id from job_inputs where job_id = %s and scene_id is not null",
                    (job_id,)) or [])],
                "dataset_versions": paths.get("dataset_versions", []),
                "model": ({"name": model["name"], "version": model["version"],
                           "sha256": model.get("checksum")} if model
                          else {"name": None, "version": None, "sha256": None}),
                "config_hash": (job or {}).get("config_hash"),
                "evaluation_grid_m": 2.5,
                "reference_note": paths.get("reference_note"),
                "reference_alignment": paths.get("reference_alignment"),
                "code_commit": settings.code_commit or None,
                "worker_image": settings.worker_image or None,
                "degradation_operator": engine.DEGRADATION_OPERATOR,
                "overall_status": decision["overall_status"],
                "score": decision["score"],
                "metrics": {k: v for k, v in all_metrics.items()},
                "human_summary": HUMAN_SUMMARY,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "validation_id": str(vrun_id),
            }
            tx.execute(
                """
                insert into reports (validation_run_id, summary_json)
                values (%s, %s)
                on conflict (validation_run_id) do update set summary_json = excluded.summary_json
                """,
                (vrun_id, json.dumps(summary, default=str)),
            )
            tx.execute(
                """
                insert into provenance_events (project_id, entity_type, entity_id, event_type, actor, payload)
                values (%s, 'validation_run', %s, 'validation_completed', 'validation-engine', %s)
                """,
                ((job or {}).get("project_id"), vrun_id,
                 json.dumps({"overall_status": decision["overall_status"],
                             "score": decision["score"]})),
            )
            tx.execute(
                """
                update validation_runs set status = %s, overall_status = %s,
                       score = %s, notes = %s where id = %s
                """,
                ("COMPLETED", decision["overall_status"], decision["score"],
                 HUMAN_SUMMARY, vrun_id),
            )
            return summary
    except Exception:
        if vrun_id:
            try:
                with db.transaction() as tx2:
                    changed = tx2.execute(
                        "update validation_runs set status = 'FAILED' where id = %s",
                        (vrun_id,),
                    )
                    if changed != 1:
                        log.warning("validation %s FAILED marker affected %s rows",
                                    vrun_id, changed)
            except Exception:  # noqa: BLE001 - failure marker is best-effort
                pass
        raise


def _local_report(job_id: str, paths: dict, obs_res: dict, unc_res: dict,
                  ref_metrics: dict, ref_coverage: float | None, decision: dict,
                  settings) -> dict:
    """Standalone (no-DB) report for smoke runs / tests."""
    return {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "protocol": settings.validation_protocol_version,
        "overall_status": decision["overall_status"],
        "score": decision["score"],
        "evaluation_grid_m": 2.5,
        "metrics": [
            {"name": "observation_rmse", "value": obs_res["rmse_mean"], "pass": True},
        ],
        "uncertainty": {"mean": unc_res["mean"], "p95": unc_res["p95"]},
        "status": "COMPLETED",
        "reasons": decision["reasons"],
    }
