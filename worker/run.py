"""Job execution: the worker.run(job) contract (PRD 8.1).

Artifact layout (immutable): local {artifact_root}/{bucket}/{project_id}/{job_id}/...
Storage object key (bucket-relative, matches the RLS policy prefix):
{project_id}/{job_id}/{artifact_type}/v1/{filename}

Workers never hold client connections: they claim jobs from Postgres, write
artifacts, upload them to Supabase Storage when configured, and let Realtime
stream state changes. Validation failures propagate — a job whose validation
cannot be completed is marked FAILED, never COMPLETED.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as shp_transform

from backend import db
from backend.config import get_settings
from backend.errors import (ApiError, ARTIFACT_WRITE_FAILED, DATA_CORRUPT,
                             MODEL_UNAVAILABLE)
from backend.queue import (complete_job_step, set_job_status, skip_job_step,
                           start_job_step)
from backend.validation import engine, runner as validation_runner
from worker import baselines, rasterio_io, tiling
from worker import preprocess as preprocess_mod
from worker.job_outputs import (build_run_metadata, write_previews,
                                write_run_metadata)
from worker.registry import MODEL_REGISTRY

log = logging.getLogger("sentry.worker")
BANDS = ["B02", "B03", "B04", "B08"]
SCALE = 4
ALL_STEPS = ["preprocess", "reconstruct", "uncertainty", "validate", "report"]


# --------------------------------------------------------------------------- #
# Artifact store: local write + optional Storage upload + DB registration
# --------------------------------------------------------------------------- #

class ArtifactStore:
    """Local artifact filesystem + Supabase Storage mirror + metadata rows."""

    def __init__(self, job: dict) -> None:
        self.job = job
        self.root = Path(get_settings().artifact_root)
        self.storage_cfg = bool(get_settings().supabase_url
                                and get_settings().supabase_service_role_key)

    def local_dir(self, bucket: str, artifact_type: str) -> Path:
        """Local path: {artifact_root}/{bucket}/{project_id}/{job_id}/{type}/v1."""
        d = self.root / bucket / self.job["project_id"] / self.job["id"] / artifact_type / "v1"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def object_key(self, artifact_type: str, filename: str) -> str:
        """Bucket-relative key: {project_id}/{job_id}/{type}/v1/{filename}."""
        return f"{self.job['project_id']}/{self.job['id']}/{artifact_type}/v1/{filename}"

    def upload(self, bucket: str, key: str, path: Path) -> None:
        """Upload to Supabase Storage; fail closed when DB-backed but unconfigured."""
        if not self.storage_cfg:
            if get_settings().supabase_db_url:
                raise ApiError(ARTIFACT_WRITE_FAILED,
                               "storage not configured for a database-backed deployment; "
                               "refusing local-only artifact registration")
            return
        import httpx

        settings = get_settings()
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{settings.storage_url}/object/{bucket}/{key}",
                    headers={
                        "authorization": f"Bearer {settings.supabase_service_role_key}",
                        "apikey": settings.supabase_service_role_key,
                        "content-type": "application/octet-stream",
                        "x-upsert": "false",
                    },
                    content=path.read_bytes(),
                )
            if resp.status_code not in (200, 201):
                raise ApiError(ARTIFACT_WRITE_FAILED,
                               f"storage upload failed ({resp.status_code}): {key}")
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001 - network/storage failures are fatal
            raise ApiError(ARTIFACT_WRITE_FAILED,
                           f"storage upload error for {key}: {exc}") from exc

    def download(self, bucket: str, key: str, dest: Path) -> Path:
        """Fetch an artifact to dest: local hit or authenticated Storage download."""
        if dest.exists():
            return dest
        if not self.storage_cfg:
            raise ApiError(DATA_CORRUPT,
                           f"artifact {bucket}/{key} not available locally and storage "
                           "is not configured")
        import httpx

        settings = get_settings()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with httpx.Client(timeout=120.0) as client:
                resp = client.get(
                    f"{settings.storage_url}/object/{bucket}/{key}",
                    headers={
                        "authorization": f"Bearer {settings.supabase_service_role_key}",
                        "apikey": settings.supabase_service_role_key,
                    },
                )
            if resp.status_code != 200:
                raise ApiError(DATA_CORRUPT,
                               f"storage download failed ({resp.status_code}): {bucket}/{key}")
            dest.write_bytes(resp.content)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001 - network failures are corrupt input
            raise ApiError(DATA_CORRUPT,
                           f"storage download error for {bucket}/{key}: {exc}") from exc
        return dest

    def register(self, artifact_type: str, bucket: str, path: Path, key: str,
                 crs: str | None = None, w: int | None = None,
                 h: int | None = None, res: float | None = None,
                 transform: list | None = None,
                 media_type: str = "image/tiff",
                 band_count: int | None = 4) -> dict:
        """Upload + insert an artifact row, with spatial metadata when present."""
        self.upload(bucket, key, path)
        wkt = None
        if crs and transform is not None and w is not None and h is not None:
            b = bounds_wgs84(transform, h, w, crs)
            wkt = (f"POLYGON(({b[0]} {b[1]},{b[2]} {b[1]},{b[2]} {b[3]},"
                   f"{b[0]} {b[3]},{b[0]} {b[1]}))")
        row = db.query(
            """
            insert into raster_artifacts
                (job_id, artifact_type, storage_bucket, object_key, checksum,
                 media_type, crs, width, height, resolution_m, band_count, bounds, bytes)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    case when %s is null then null else ST_GeomFromText(%s, 4326) end,
                    %s)
            returning id
            """,
            (self.job["id"], artifact_type, bucket, key,
             rasterio_io.sha256_file(path), media_type, crs, w, h, res,
             band_count, wkt, wkt, path.stat().st_size),
            one=True,
        )
        return {**(row or {"id": "local"}), "object_key": key,
                "storage_bucket": bucket}


def bounds_wgs84(transform: list, h: int, w: int, crs: str) -> list:
    """Raster-CRS bounds -> EPSG:4326 [xmin, ymin, xmax, ymax] (oracle finding #5)."""
    a, _, c, _, e, f = (list(transform) + [0] * 6)[:6]
    poly = box(min(c, c + a * w), min(f, f + e * h), max(c, c + a * w),
               max(f, f + e * h))
    if not crs:
        raise ApiError(DATA_CORRUPT, "cannot register artifact bounds without CRS")
    if crs.upper() not in ("EPSG:4326", "WGS84"):
        try:
            tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
            poly = shp_transform(tr.transform, poly)
        except Exception as exc:
            raise ApiError(DATA_CORRUPT,
                           f"cannot transform artifact bounds {crs}->EPSG:4326: {exc}") from exc
    xmin, ymin, xmax, ymax = poly.bounds
    return [float(xmin), float(ymin), float(xmax), float(ymax)]


# --------------------------------------------------------------------------- #
# Scene loading: georeferencing from the rasters, multi-frame aware
# --------------------------------------------------------------------------- #

def _load_scene_frames(job_id: str) -> list[dict]:
    """Load every input scene of a job as a frame with its OWN raster georef.

    Band completeness is validated against scene_bands (exactly B02..B08 with
    one row each); the stored per-band scale_factor is used instead of
    magnitude heuristics (oracle findings #6, #18, #19).
    """
    inputs = db.query(
        "select scene_id from job_inputs where job_id = %s and scene_id is not null",
        (job_id,)) or []
    if not inputs:
        raise ApiError(DATA_CORRUPT, f"job {job_id} has no scene inputs")
    root = Path(get_settings().artifact_root)
    frames: list[dict] = []
    for row in inputs:
        band_rows = db.query(
            "select band_name, object_key, scale_factor from scene_bands where scene_id = %s",
            (row["scene_id"],)) or []
        by_band: dict[str, dict] = {}
        for br in band_rows:
            if br["band_name"] in by_band:
                raise ApiError(DATA_CORRUPT,
                               f"duplicate band rows for scene {row['scene_id']}")
            by_band[br["band_name"]] = br
        missing = [b for b in BANDS
                   if b not in by_band or not by_band[b]["object_key"]]
        if missing:
            raise ApiError(DATA_CORRUPT,
                           f"scene {row['scene_id']} missing staged bands: {missing}")

        arrays: list[np.ndarray] = []
        georef: dict | None = None
        for b in BANDS:
            key = by_band[b]["object_key"]
            p = root / key
            if not p.exists():
                p = root / "scene-assets" / key
            if not p.exists():
                raise ApiError(DATA_CORRUPT, f"scene band file not staged: {p}")
            r = rasterio_io.read_raster(p)
            arr = r["array"][0] if r["array"].ndim == 3 else r["array"]
            scale = float(by_band[b]["scale_factor"] or 1.0)
            if np.issubdtype(np.dtype(r["dtype"]), np.integer):
                arr = np.clip(arr.astype(np.float32) * scale, 0.0, 1.0)
            arrays.append(arr.astype(np.float32))
            if georef is None:
                georef = r
            elif (r["crs"], r["width"], r["height"]) != \
                    (georef["crs"], georef["width"], georef["height"]):
                raise ApiError(DATA_CORRUPT,
                               f"band {b} grid mismatch for scene {row['scene_id']}")
            elif not np.allclose(r["transform"], georef["transform"]):
                raise ApiError(DATA_CORRUPT,
                               f"band {b} transform mismatch for scene {row['scene_id']}")
        frame = np.stack(arrays, axis=0).astype(np.float32)
        frame = np.clip(frame, 0.0, 1.0)
        valid = np.isfinite(frame).all(axis=0)
        if georef is None:  # pragma: no cover - unreachable: BANDS is non-empty
            raise ApiError(DATA_CORRUPT, "no band rasters loaded")
        frames.append({"reflectance": frame, "valid": valid,
                       "crs": georef["crs"], "transform": georef["transform"]})

    # Multi-frame fusion requires one common grid.
    ref = frames[0]
    for fr in frames[1:]:
        if (fr["reflectance"].shape != ref["reflectance"].shape
                or fr["crs"] != ref["crs"]
                or not np.allclose(fr["transform"], ref["transform"])):
            raise ApiError(DATA_CORRUPT,
                           "input scenes are not co-registered to a common grid")
    return frames


# --------------------------------------------------------------------------- #
# Execution entrypoint
# --------------------------------------------------------------------------- #

def run(job: dict) -> list[dict]:
    """Execute one CLAIMED job; failures mark the job FAILED and re-raise."""
    try:
        if job["job_type"] == "preprocess":
            arts = _run_preprocess(job)
        elif job["job_type"] == "reconstruct":
            arts = _run_reconstruct(job)
        elif job["job_type"] == "validate":
            arts = _run_validate(job)
        elif job["job_type"] == "benchmark":
            arts = _run_benchmark(job)
        else:
            raise ApiError(DATA_CORRUPT, f"unknown job_type {job['job_type']}")
    except ApiError as exc:
        _fail(job, exc.code, exc.message)
        raise
    except Exception as exc:  # noqa: BLE001 - crash containment with GPU-OOM mapping
        msg = str(exc)
        code = "GPU_OOM" if ("out of memory" in msg.lower() or "cuda" in msg.lower()) \
            else DATA_CORRUPT
        _fail(job, code, msg)
        raise
    return arts


def _fail(job: dict, code: str, message: str) -> None:
    """Mark job FAILED; partial artifacts are never presented as complete."""
    log.error("job %s failed (%s): %s", job["id"], code, message)
    try:
        set_job_status(job["id"], "FAILED", error_code=code, error_message=message[:500])
    except Exception:  # noqa: BLE001
        pass


def _finish_steps(job_id: str, completed: list[str]) -> None:
    """Skip applicable-but-unrun steps; steps absent from this mode are ignored."""
    from backend.errors import NOT_FOUND as _NOT_FOUND

    for step in ALL_STEPS:
        if step not in completed:
            try:
                skip_job_step(job_id, step)
            except ApiError as exc:
                if exc.code != _NOT_FOUND:
                    raise


def _preprocess_frame(frame: dict) -> dict:
    """Preprocess one reflectance frame (converts back to DN for the scaler)."""
    return preprocess_mod.preprocess({
        "bands": {b: frame["reflectance"][i] for i, b in enumerate(BANDS)},
        "valid": frame["valid"], "crs": frame["crs"],
        "transform": frame["transform"],
        "scale_factor": 1.0,
    })


# --------------------------------------------------------------------------- #
# preprocess
# --------------------------------------------------------------------------- #

def _run_preprocess(job: dict) -> list[dict]:
    """Standardize + tile every input frame; register tile + manifest artifacts."""
    store = ArtifactStore(job)
    start_job_step(job["id"], "preprocess")
    set_job_status(job["id"], "PREPROCESSING", progress=0.1)
    frames = _load_scene_frames(job["id"])

    pre = _preprocess_frame(frames[0])
    tiles = tiling.extract_tiles(pre["reflectance"], pre["valid"])
    h, w = pre["reflectance"].shape[1:]
    tiles_path = store.local_dir("scene-assets", "preprocessed_tiles") / "tiles.npz"
    np.savez_compressed(
        tiles_path,
        reflectance=pre["reflectance"],
        valid=pre["valid"],
        shape=np.array([4, h, w]),
        transform=np.array(frames[0]["transform"], dtype=float),
        crs=np.array([frames[0]["crs"]]),
        fingerprint=np.array([pre["meta"]["fingerprint"]]),
    )
    art = store.register("preprocessed_tiles", "scene-assets", tiles_path,
                         store.object_key("preprocessed_tiles", "tiles.npz"),
                         frames[0]["crs"], w, h, 10.0, frames[0]["transform"],
                         media_type="application/x-npz", band_count=4)

    manifest = store.local_dir("scene-assets", "manifest") / "manifest.json"
    manifest.write_text(json.dumps({
        "job_id": job["id"], "fingerprint": pre["meta"]["fingerprint"],
        "tile_count": len(tiles), "shape": [4, h, w], "crs": frames[0]["crs"],
        "transform": frames[0]["transform"], "bands": BANDS,
        "frames": len(frames),
    }))
    m_art = store.register("manifest", "scene-assets", manifest,
                           store.object_key("manifest", "manifest.json"),
                           media_type="application/json", band_count=None)

    complete_job_step(job["id"], "preprocess",
                      {"tiles": len(tiles), "fingerprint": pre["meta"]["fingerprint"]})
    _finish_steps(job["id"], ["preprocess"])
    set_job_status(job["id"], "COMPLETED", progress=1.0)
    return [art, m_art]


# --------------------------------------------------------------------------- #
# reconstruct
# --------------------------------------------------------------------------- #

def _load_tiles(job: dict, frames: list[dict]):
    """Return (lr_tiles, frame_tiles, shape, transform, crs).

    lr_tiles: tiles of the base frame with weights.
    frame_tiles: per tile index, one (B, th, tw) array per temporal frame —
    the multi-temporal input required by custom_mf_sr (oracle finding #21).
    """
    art = db.query(
        """
        select object_key from raster_artifacts
        where job_id = %s and artifact_type = 'preprocessed_tiles' limit 1
        """,
        (job["id"],), one=True)
    if art is not None and art.get("object_key"):
        p = Path(get_settings().artifact_root) / "scene-assets" / art["object_key"]
        if p.exists():
            data = np.load(p, allow_pickle=False)
            shape = tuple(int(x) for x in data["shape"])
            if "reflectance" in data.files:
                base = data["reflectance"]
                valid = data["valid"]
                lr_tiles = tiling.extract_tiles(base, valid)
            else:  # backward-compatible read of early dev artifacts
                lr_tiles = [{"pixels": px, "weight": wt, "valid": v,
                             "origin": tuple(int(o) for o in og)}
                            for px, wt, v, og in zip(data["pixels"], data["weights"],
                                                    data["valid"], data["origins"])]
            frame_tiles = [[t["pixels"] for t in lr_tiles]]
            for fr in frames[1:]:  # same windows across temporal frames
                pre = _preprocess_frame(fr)
                extra = []
                for t in lr_tiles:
                    r0, c0 = t["origin"]
                    th, tw = t["pixels"].shape[1:]
                    extra.append(pre["reflectance"][:, r0:r0 + th, c0:c0 + tw])
                frame_tiles.append(extra)
            return lr_tiles, frame_tiles, shape, \
                data["transform"].astype(float).tolist(), str(data["crs"][0])

    # Inline fallback (single-job dev flow): preprocess every frame directly.
    pre0 = _preprocess_frame(frames[0])
    lr_tiles = tiling.extract_tiles(pre0["reflectance"], frames[0]["valid"])
    frame_tiles = [[t["pixels"] for t in lr_tiles]]
    for fr in frames[1:]:
        pre = _preprocess_frame(fr)
        ft = tiling.extract_tiles(pre["reflectance"], fr["valid"])
        frame_tiles.append([t["pixels"] for t in ft])
    return lr_tiles, frame_tiles, tuple(pre0["reflectance"].shape), \
        frames[0]["transform"], frames[0]["crs"]


def _model_name(job: dict) -> str:
    row = db.query("select name from model_versions where id = %s",
                   (job.get("model_version_id"),), one=True) \
        if job.get("model_version_id") else None
    return row["name"] if row else "bicubic_4x"


def _stitch_sr(sr_tiles: list[dict], shape: tuple, scale: int) -> np.ndarray:
    """Feathered stitching on the SR grid using carried tile weights (#20)."""
    _, h, w = shape
    H, W = h * scale, w * scale
    stitched = np.zeros((4, H, W), dtype=np.float32)
    wsum = np.zeros((H, W), dtype=np.float32)
    for t in sr_tiles:
        r0, c0 = t["origin"]
        px = t["pixels"]
        wgt = t.get("weight")
        if wgt is None:
            wgt = np.ones(px.shape[1:], dtype=np.float32)
        r1, c1 = r0 * scale + px.shape[1], c0 * scale + px.shape[2]
        stitched[:, r0 * scale:r1, c0 * scale:c1] += px * wgt[None]
        wsum[r0 * scale:r1, c0 * scale:c1] += wgt
    mask = wsum > 0
    stitched[:, mask] /= wsum[mask][None, :]
    return stitched


def _upscale_weight(weight: Any, scale: int) -> Any:
    """Feather weights carried from the LR grid onto the SR grid."""
    from skimage.transform import resize as _resize

    if weight is None:
        return None  # stitcher substitutes uniform weights
    # Boolean validity masks cannot be anti-aliased (skimage raises); smooth
    # float weights (feather windows) can and should be.
    anti_aliasing = not np.issubdtype(np.asarray(weight).dtype, np.bool_)
    return _resize(weight, (weight.shape[0] * scale, weight.shape[1] * scale),
                   anti_aliasing=anti_aliasing, preserve_range=True).astype(np.float32)


def _sr_weight(tile: dict, scale: int) -> np.ndarray | None:
    """Feather weights multiplied by the upscaled valid-data mask."""
    feather = _upscale_weight(tile.get("weight"), scale)
    valid = _upscale_weight(tile.get("valid", np.ones(tile["pixels"].shape[1:])), scale)
    if valid is None:
        return feather
    return valid if feather is None else feather * valid


def _input_products(job_id: str) -> list[dict]:
    """Product provenance for run_metadata.json: one row per staged input scene.

    Reads what the ingest path actually recorded (provider product id, sensing
    time, tile id, processing baseline) — never inferred or defaulted.
    """
    rows = db.query(
        """
        select s.provider_product_id, s.sensing_time, s.metadata
          from job_inputs ji
          join scenes s on s.id = ji.scene_id
         where ji.job_id = %s and ji.scene_id is not null
         order by s.sensing_time asc nulls last
        """,
        (job_id,)) or []
    products = []
    for r in rows:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):  # psycopg returns jsonb as dict; be tolerant
            try:
                meta = json.loads(meta)
            except (TypeError, ValueError):
                meta = {}
        products.append({
            "provider_product_id": r.get("provider_product_id"),
            "sensing_time": r.get("sensing_time"),
            "tile_id": meta.get("tile_id"),
            "processing_baseline": meta.get("processing_baseline"),
        })
    return products


def _run_reconstruct(job: dict) -> list[dict]:
    """Run the selected model; write SR + uncertainty; validation must pass."""
    store = ArtifactStore(job)
    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.monotonic()
    set_job_status(job["id"], "PREPROCESSING", progress=0.05)
    start_job_step(job["id"], "preprocess")
    frames = _load_scene_frames(job["id"])
    lr_tiles, frame_tiles, shape, transform, crs = _load_tiles(job, frames)
    complete_job_step(job["id"], "preprocess",
                      {"mode": "inline", "tiles": len(lr_tiles)})

    start_job_step(job["id"], "reconstruct")
    set_job_status(job["id"], "RECONSTRUCTING", progress=0.2)
    model_name = _model_name(job)
    reg = MODEL_REGISTRY.get(model_name)
    if reg is None:
        raise ApiError(MODEL_UNAVAILABLE, f"model {model_name} not in registry")
    if reg.get("visual_only"):
        raise ApiError(MODEL_UNAVAILABLE,
                       f"{model_name} is visual-only and can never be a scientific output")

    if model_name == "bicubic_4x":
        sr_tiles = [{"origin": t["origin"], "pixels": baselines.run_bicubic(t["pixels"]),
                     "weight": _sr_weight(t, SCALE)}
                    for t in lr_tiles]
    elif model_name == "opensr_ldsrs2":
        sr_tiles = [{"origin": t["origin"], "pixels": baselines.run_opensr(t["pixels"]),
                     "weight": _sr_weight(t, SCALE)}
                    for t in lr_tiles]
    else:  # custom_mf_sr: TRUE multi-frame fusion (one list per tile window)
        sr_tiles = []
        for i, t in enumerate(lr_tiles):
            window_frames = [ft[i] for ft in frame_tiles if i < len(ft)]
            sr_px, _ = baselines.run_custom_mf(window_frames)
            sr_tiles.append({"origin": t["origin"], "pixels": sr_px,
                             "weight": _sr_weight(t, SCALE)})

    stitched = _stitch_sr(sr_tiles, shape, SCALE)
    _, h, w = shape
    sr_transform = [transform[0] / SCALE, 0, transform[2], 0, transform[4] / SCALE,
                    transform[5]]
    unc = baselines.uncertainty_proxy(stitched)

    sr_path = store.local_dir("sr-outputs", "sr_output") / "sr.tif"
    rasterio_io.write_cog(sr_path, stitched, crs, sr_transform, BANDS, resolution_m=2.5)
    unc_path = store.local_dir("uncertainty", "uncertainty") / "uncertainty.tif"
    rasterio_io.write_cog(unc_path, unc, crs, sr_transform, ["uncertainty"],
                         resolution_m=2.5)

    sr_art = store.register("sr_output", "sr-outputs", sr_path,
                            store.object_key("sr_output", "sr.tif"),
                            crs, w * SCALE, h * SCALE, 2.5, sr_transform)
    complete_job_step(job["id"], "reconstruct", {"model": model_name, "grid_m": 2.5})
    set_job_status(job["id"], "UNCERTAINTY", progress=0.6)
    start_job_step(job["id"], "uncertainty")

    unc_art = store.register("uncertainty", "uncertainty", unc_path,
                             store.object_key("uncertainty", "uncertainty.tif"),
                             crs, w * SCALE, h * SCALE, 2.5, sr_transform)
    complete_job_step(job["id"], "uncertainty", {"proxy": "gradient_magnitude_p99"})

    # PRD §11 outputs: previews + run metadata (visualization only, never data).
    previews = write_previews(
        stitched, np.ones((h * SCALE, w * SCALE), dtype=bool),
        store.local_dir("previews", "preview_rgb"),
        false_color_dir=store.local_dir("previews", "preview_false_color"))
    rgb_art = store.register(
        "preview_rgb", "previews", previews["preview_rgb.png"]["path"],
        store.object_key("preview_rgb", "preview_rgb.png"),
        media_type="image/png", band_count=3)
    fcv_art = store.register(
        "preview_false_color", "previews", previews["preview_false_color.png"]["path"],
        store.object_key("preview_false_color", "preview_false_color.png"),
        media_type="image/png", band_count=3)
    fc_meta = store.local_dir("previews", "run_metadata") / "run_metadata.json"
    meta_payload = build_run_metadata(
        job, model_name=model_name, crs=crs, transform=sr_transform, grid_m=2.5,
        input_products=_input_products(job["id"]), frame_count=len(frames),
        sampling_steps=None, runtime_s=time.monotonic() - t0,
        started_utc=started_utc)
    write_run_metadata(fc_meta, meta_payload)
    meta_art = store.register(
        "run_metadata", "previews", fc_meta,
        store.object_key("run_metadata", "run_metadata.json"),
        media_type="application/json", band_count=None)

    if job.get("mode") != "reconstruct_validate":
        # Pure reconstruct: no validation/report steps exist for this mode.
        _finish_steps(job["id"], ["preprocess", "reconstruct", "uncertainty"])
        set_job_status(job["id"], "COMPLETED", progress=1.0)
        return [sr_art, unc_art, rgb_art, fcv_art, meta_art]
    set_job_status(job["id"], "VALIDATING", progress=0.7)

    # Validation is mandatory for reconstruct_validate jobs; failure fails the job (#8).
    start_job_step(job["id"], "validate")
    obs_path = _observation_for(job, store, frames)
    ref_path = _reference_for(job["id"])
    summary = validation_runner.run_validation(job["id"], {
        "sr": str(sr_path), "uncertainty": str(unc_path),
        "observation": str(obs_path),
        "reference": str(ref_path) if ref_path else None,
        "dataset_versions": _dataset_versions(job["id"]),
        "reference_note": "reference comparison per protocol sih26142_v1"
        if ref_path else None,
    })

    report_path = store.local_dir("reports", "report_file") / "report.json"
    set_job_status(job["id"], "REPORTING", progress=0.9)
    start_job_step(job["id"], "report")
    report_path.write_text(json.dumps(summary, indent=2, default=str))
    report_art = store.register(
        "report_file", "reports", report_path,
        store.object_key("report_file", "report.json"),
        media_type="application/json", band_count=None)
    if summary.get("validation_id"):
        db.execute(
            "update reports set report_object_key = %s where validation_run_id = %s",
            (report_art["object_key"], summary["validation_id"]),
        )
    complete_job_step(job["id"], "validate",
                      {"overall_status": summary.get("overall_status")})
    complete_job_step(job["id"], "report", {"report": "report.json"})
    _finish_steps(job["id"], ["preprocess", "reconstruct", "uncertainty",
                               "validate", "report"])
    set_job_status(job["id"], "COMPLETED", progress=1.0)
    return [sr_art, unc_art, rgb_art, fcv_art, meta_art]


def _observation_for(job: dict, store: ArtifactStore, frames: list[dict]) -> Path:
    """Locate or (re)write the 10 m observation COG for consistency checks."""
    row = db.query(
        """
        select object_key from raster_artifacts
        where job_id = %s and artifact_type = 'observation' limit 1
        """,
        (job["id"],), one=True)
    if row is not None and row.get("object_key"):
        p = Path(get_settings().artifact_root) / "scene-assets" / row["object_key"]
        if p.exists():
            return p
    p = store.local_dir("scene-assets", "observation") / "observation.tif"
    rasterio_io.write_cog(p, frames[0]["reflectance"], frames[0]["crs"],
                          frames[0]["transform"], BANDS, resolution_m=10.0)
    store.register("observation", "scene-assets", p,
                   store.object_key("observation", "observation.tif"),
                   frames[0]["crs"], frames[0]["reflectance"].shape[2],
                   frames[0]["reflectance"].shape[1], 10.0, frames[0]["transform"])
    return p


def _reference_for(job_id: str) -> str | None:
    """Resolve a reference asset from job_inputs and stage it (finding #11)."""
    row = db.query(
        """
        select ra.object_key from reference_assets ra
        join job_inputs ji on ji.ref_asset_id = ra.id
        where ji.job_id = %s limit 1
        """,
        (job_id,), one=True)
    if row is None or not row.get("object_key"):
        return None
    p = Path(get_settings().artifact_root) / "references" / row["object_key"]
    if not p.exists():
        raise ApiError(DATA_CORRUPT, f"reference asset not staged: {p}")
    return str(p)


def _reference_by_id(ref_id: str) -> str:
    """Resolve the exact request-scoped reference; fail closed when unusable."""
    row = db.query(
        "select object_key from reference_assets where id = %s",
        (ref_id,), one=True)
    if row is None:
        raise ApiError(DATA_CORRUPT, f"reference asset {ref_id} not found")
    if not row.get("object_key"):
        raise ApiError(DATA_CORRUPT,
                       f"reference asset {ref_id} has no staged object")
    p = Path(get_settings().artifact_root) / "references" / row["object_key"]
    if not p.exists():
        raise ApiError(DATA_CORRUPT, f"reference asset not staged: {p}")
    return str(p)


def _dataset_versions(job_id: str) -> list[str]:
    """Real dataset versions from the scenes actually used (finding #25)."""
    rows = db.query(
        """
        select distinct ds.name, ds.version from dataset_sources ds
        join scenes s on s.dataset_source_id = ds.id
        join job_inputs ji on ji.scene_id = s.id
        where ji.job_id = %s
        """,
        (job_id,)) or []
    return [f"{r['name']}:{r['version']}" for r in rows]


# --------------------------------------------------------------------------- #
# validate / benchmark
# --------------------------------------------------------------------------- #

def _artifact_path(bucket: str, artifact_type: str, job_id: str) -> Path:
    row = db.query(
        """
        select storage_bucket, object_key from raster_artifacts
        where job_id = %s and artifact_type = %s limit 1
        """,
        (job_id, artifact_type), one=True)
    if row is None or not row.get("object_key"):
        raise ApiError(DATA_CORRUPT, f"no {artifact_type} artifact for job {job_id}")
    key = row["object_key"]
    store_bucket = row.get("storage_bucket") or bucket
    local = Path(get_settings().artifact_root) / bucket / key
    if local.exists():
        return local
    legacy = Path(get_settings().artifact_root) / "scene-assets" / key
    if legacy.exists():
        return legacy
    # Cross-worker fallback: fetch from Storage into the canonical local path.
    return ArtifactStore({"project_id": "probe", "id": job_id}).download(
        store_bucket, key, local)


def _source_job_id(job: dict) -> str:
    """A validate-wrapper job carries its source job in job_inputs (role='source_job')."""
    row = db.query(
        """
        select object_key_snapshot from job_inputs
        where job_id = %s and role = 'source_job' limit 1
        """,
        (job["id"],), one=True)
    if row is None or not row.get("object_key_snapshot"):
        return job["id"]  # self-contained job: validate its own artifacts
    return row["object_key_snapshot"]


def _run_validate(job: dict) -> list[dict]:
    """Dedicated validation job: validate + report steps on the SOURCE job."""
    from backend.queue import fail_job_step

    store = ArtifactStore(job)
    source = _source_job_id(job)
    is_wrapper = source != job["id"]
    start_job_step(job["id"], "validate")
    set_job_status(job["id"], "VALIDATING", progress=0.5)
    validation_id: str | None = None
    try:
        vrun = db.query(
            "select id, job_id, reference_id from validation_runs where queue_job_id = %s limit 1",
            (job["id"],), one=True)
        if vrun is not None and vrun.get("job_id") != source:
            raise ApiError(DATA_CORRUPT, "validation wrapper/source job mismatch")
        if vrun is None and is_wrapper:
            raise ApiError(DATA_CORRUPT,
                           "validation wrapper has no linked validation run")
        validation_id = vrun["id"] if vrun else None
        if vrun is not None and vrun.get("reference_id"):
            ref_path = _reference_by_id(vrun["reference_id"])
        else:
            ref_path = _reference_for(job["id"]) or _reference_for(source)
        sr_path = _artifact_path("sr-outputs", "sr_output", source)
        unc_path = _artifact_path("uncertainty", "uncertainty", source)
        obs_path = _artifact_path("scene-assets", "observation", source)
        paths: dict = {
            "sr": str(sr_path), "uncertainty": str(unc_path),
            "observation": str(obs_path),
            "reference": str(ref_path) if ref_path else None,
            "dataset_versions": _dataset_versions(source),
        }
        if validation_id:
            paths["validation_id"] = validation_id
        summary = validation_runner.run_validation(source, paths)
        report_path = store.local_dir("reports", "report_file") / "report.json"
        report_path.write_text(json.dumps(summary, indent=2, default=str))
        store.register("report_file", "reports", report_path,
                       store.object_key("report_file", "report.json"),
                       media_type="application/json", band_count=None)
        complete_job_step(job["id"], "validate",
                          {"overall_status": summary.get("overall_status")})
        set_job_status(job["id"], "REPORTING", progress=0.9)
        start_job_step(job["id"], "report")
        complete_job_step(job["id"], "report", {})
        _finish_steps(job["id"], ["validate", "report"])
        set_job_status(job["id"], "COMPLETED", progress=1.0)
        return []
    except Exception:
        if validation_id:
            try:
                db.execute(
                    "update validation_runs set status = 'FAILED' where id = %s",
                    (validation_id,),
                )
            except Exception:  # noqa: BLE001 - best-effort failure marker
                pass
        for step in ("validate", "report"):
            try:
                fail_job_step(job["id"], step, DATA_CORRUPT, "validation failed")
            except Exception:  # noqa: BLE001 - step may already be terminal
                pass
        raise


def _run_benchmark(job: dict) -> list[dict]:
    """Benchmark: both models on identical inputs, each scored independently
    against the observation grid (Component G semantics, finding #22)."""
    store = ArtifactStore(job)
    start_job_step(job["id"], "preprocess")
    frames = _load_scene_frames(job["id"])
    pre = _preprocess_frame(frames[0])
    complete_job_step(job["id"], "preprocess", {"mode": "inline"})

    start_job_step(job["id"], "validate")
    set_job_status(job["id"], "VALIDATING", progress=0.3)
    side = min(256, pre["reflectance"].shape[1], pre["reflectance"].shape[2])
    if side < 64:
        raise ApiError(DATA_CORRUPT, "scene too small to benchmark")
    lr = pre["reflectance"][:, :side, :side]
    obs_tile = np.moveaxis(lr, 0, -1)  # the identical evaluation target

    bic = baselines.run_bicubic(lr)
    temporal = [fr["reflectance"][:, :side, :side] for fr in frames]
    cus, _ = baselines.run_custom_mf(temporal)

    def _score(sr: np.ndarray) -> dict:
        sr_bhwc = np.moveaxis(sr, 0, -1)
        oc = engine.observation_consistency(sr_bhwc, obs_tile)
        from skimage.transform import resize
        down = np.stack([
            resize(sr_bhwc[..., i], obs_tile.shape[:2], anti_aliasing=True,
                   preserve_range=True) for i in range(4)
        ], axis=-1).astype(np.float32)
        sf = engine.spatial_fidelity(down, obs_tile)
        return {"observation_rmse": oc["rmse_mean"],
                "psnr": sf["psnr"], "ssim": sf["ssim"]}

    custom_m, baseline_m = _score(cus), _score(bic)
    delta = engine.benchmark_delta(custom_m, baseline_m)

    sr_transform = [frames[0]["transform"][0] / SCALE, 0, frames[0]["transform"][2],
                    0, frames[0]["transform"][4] / SCALE, frames[0]["transform"][5]]
    p = store.local_dir("benchmarks", "benchmark_output") / "benchmark.json"
    p.write_text(json.dumps({
        "models": {"custom": custom_m, "bicubic": baseline_m},
        "deltas": delta,
        "note": "both models evaluated on the identical tile against the same "
                "observation grid",
    }, indent=2, default=float))
    art = store.register("benchmark_output", "benchmarks", p,
                         store.object_key("benchmark_output", "benchmark.json"),
                         media_type="application/json", band_count=None)
    complete_job_step(job["id"], "validate", delta)
    start_job_step(job["id"], "report")
    complete_job_step(job["id"], "report", {"artifact": "benchmark.json"})
    _finish_steps(job["id"], ["preprocess", "validate", "report"])
    set_job_status(job["id"], "COMPLETED", progress=1.0)
    return [art]
