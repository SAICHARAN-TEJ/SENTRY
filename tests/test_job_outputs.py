"""PRD §11 output-schema tests: previews, run_metadata.json, full reconstruct."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from worker import job_outputs
from worker.job_outputs import (build_run_metadata, write_previews,
                                write_run_metadata)


# --------------------------------------------------------------------------- #
# Previews
# --------------------------------------------------------------------------- #

def _sr() -> np.ndarray:
    """Deterministic (4, 32, 24) reflectance with spatial structure."""
    r = np.random.default_rng(7)
    base = np.linspace(0.05, 0.6, 32 * 24).reshape(1, 32, 24).astype(np.float32)
    noise = r.normal(0, 0.02, (4, 32, 24)).astype(np.float32)
    return np.clip(base + noise, 0, 1)


def test_previews_write_rgb_and_false_color(tmp_path):
    valid = np.ones((32, 24), dtype=bool)
    out = write_previews(_sr(), valid, tmp_path)
    assert set(out) == {"preview_rgb.png", "preview_false_color.png"}
    for name, info in out.items():
        p = tmp_path / name
        assert p.exists() and p.stat().st_size > 0
        img = Image.open(p)
        assert img.format == "PNG" and img.mode == "RGB"
        assert img.size[0] == info["width"]
        # The strip adds 18 rows below the data rows.
        assert img.size[1] == info["height"] + info["strip_h"]
    # False color is 1 px taller only via the shared caption strip; both
    # previews share the SR dimensions on their data rows.
    assert out["preview_rgb.png"]["width"] == 24
    assert out["preview_rgb.png"]["height"] == 32


def test_previews_caption_strip_present(tmp_path):
    """The caption strip rows exist below the image (self-evident labeling)."""
    valid = np.ones((16, 16), dtype=bool)
    write_previews(np.full((4, 16, 16), 0.3, np.float32), valid, tmp_path)
    img = np.asarray(Image.open(tmp_path / "preview_rgb.png"))
    assert img.shape[0] == 16 + 18  # data rows + strip
    # Strip is black except the light-gray caption glyphs drawn onto it.
    strip = img[16:]
    assert strip.mean() < 20
    assert (strip == 0).mean() > 0.9
    assert (strip > 0).any()
    assert (img[:16] > 0).any()     # data rows render content


def test_previews_invalid_pixels_render_black(tmp_path):
    sr = _sr()
    valid = np.ones((32, 24), dtype=bool)
    valid[:, :6] = False  # left band invalid
    write_previews(sr, valid, tmp_path)
    img = np.asarray(Image.open(tmp_path / "preview_rgb.png"))
    # Invalid columns are 0 across the data rows (not stretched scene values).
    assert (img[:32, :6] == 0).all()
    assert (img[:32, 10:] > 0).any()


def test_previews_constant_band_no_crash(tmp_path):
    """A constant (flat) band must not divide by zero; renders mid-gray."""
    sr = np.full((4, 8, 8), 0.25, dtype=np.float32)
    out = write_previews(sr, np.ones((8, 8), bool), tmp_path)
    img = np.asarray(Image.open(out["preview_rgb.png"]["path"]))
    assert img[:8, :8].min() == 128 and img[:8, :8].max() == 128


# --------------------------------------------------------------------------- #
# run_metadata.json
# --------------------------------------------------------------------------- #

def _job() -> dict:
    return {"id": "job-1", "project_id": "p1", "mode": "reconstruct_validate",
            "model_version_id": "00000000-0000-4000-8000-000000000009"}


def test_metadata_contains_all_prd_fields(monkeypatch):
    monkeypatch.setenv("CODE_COMMIT", "abc1234")
    monkeypatch.setenv("VALIDATION_PROTOCOL_VERSION", "sih26142_v1")
    from backend.config import get_settings
    get_settings.cache_clear()

    products = [{"provider_product_id": "S2A_MSIL2A_20260827T100701_N0512_R022_T33TTG",
                 "sensing_time": "2026-08-27T10:07:01+00:00",
                 "tile_id": "T33TTG", "processing_baseline": "N0512"}]
    meta = build_run_metadata(
        _job(), model_name="bicubic_4x", crs="EPSG:32633",
        transform=[2.5, 0, 600000, 0, -2.5, 5000000], grid_m=2.5,
        input_products=products, frame_count=1, runtime_s=1.234,
        started_utc="2026-09-12T00:00:00+00:00")

    # PRD Table 9: traceability fields.
    assert meta["job_id"] == "job-1" and meta["project_id"] == "p1"
    assert meta["model"]["name"] == "bicubic_4x"
    assert meta["model"]["sampling_steps"] is None
    assert "deterministic" in meta["model"]["note"]
    assert meta["inputs"]["frame_count"] == 1
    assert meta["inputs"]["products"][0]["provider_product_id"].startswith("S2A_")
    assert meta["inputs"]["products"][0]["tile_id"] == "T33TTG"
    assert meta["inputs"]["products"][0]["processing_baseline"] == "N0512"
    assert meta["grid"]["grid_m"] == 2.5 and meta["grid"]["crs"] == "EPSG:32633"
    assert meta["grid"]["bands"] == ["B02", "B03", "B04", "B08"]
    assert meta["grid"]["transform"][0] == 2.5
    assert meta["provenance"]["code_commit"] == "abc1234"
    assert len(meta["provenance"]["config_hash"]) == 64  # sha256 hex
    assert meta["runtime"]["runtime_s"] == 1.234
    assert meta["runtime"]["device"] in ("cpu",) or meta["runtime"]["device"].startswith("cuda")
    get_settings.cache_clear()


def test_metadata_file_roundtrip(tmp_path):
    meta = build_run_metadata(_job(), model_name="custom_mf_sr", crs="EPSG:32633",
                              transform=[2.5, 0, 0, 0, -2.5, 0], grid_m=2.5)
    p = write_run_metadata(tmp_path / "run_metadata.json", meta)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["schema"] == "sentry.run_metadata.v1"
    assert loaded["model"]["name"] == "custom_mf_sr"


def test_config_hash_is_deterministic_and_content_sensitive(monkeypatch):
    monkeypatch.setenv("JOB_LEASE_SECONDS", "300")
    from backend.config import get_settings
    get_settings.cache_clear()
    h1 = job_outputs._config_hash()
    h2 = job_outputs._config_hash()
    assert h1 == h2  # stable within a process
    monkeypatch.setenv("MAX_TILE_PIXELS", "2048")
    job_outputs._CONFIG_HASH_CACHE = None
    get_settings.cache_clear()
    h3 = job_outputs._config_hash()
    assert h3 != h1  # content-sensitive
    job_outputs._CONFIG_HASH_CACHE = None
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Full _run_reconstruct integration (offline, FakeDB)
# --------------------------------------------------------------------------- #

@pytest.fixture
def reconstruct_env(fake_db, tmp_path, monkeypatch):
    """A staged scene + job so _run_reconstruct can run end to end."""
    import sys

    from fixtures.make_fixtures import build_scene

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
    scene = build_scene(seed=42)

    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DEV_AUTH", "true")
    from backend.config import get_settings
    get_settings.cache_clear()

    model_id = fake_db.add_model("bicubic_4x", "1.0.0")
    scene_id = "00000000-0000-4000-8000-0000000004d2"
    # Stage the four band files where _load_scene_frames expects them.
    root = tmp_path / "artifacts"
    for i, band in enumerate(["B02", "B03", "B04", "B08"]):
        key = f"scenes/{scene_id}/{band}.tif"
        p = root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        import rasterio
        from rasterio.transform import from_origin
        arr = (scene["bands"][band]).astype("uint16")
        with rasterio.open(p, "w", driver="GTiff", height=arr.shape[0],
                           width=arr.shape[1], count=1, dtype="uint16",
                           crs="EPSG:32633",
                           transform=from_origin(600000, 5000000, 10, 10)) as dst:
            dst.write(arr, 1)
    fake_db.scenes[scene_id] = {
        "id": scene_id, "provider_product_id": "S2A_MSIL2A_20260827T100701_N0512_R022_T33TTG",
        "dataset_source_id": "ds-1", "sensing_time": "2026-08-27T10:07:01+00:00",
        "metadata": {"tile_id": "T33TTG", "processing_baseline": "N0512"},
        "crs": "EPSG:32633", "resolution_m": 10.0}
    fake_db.dataset_sources[("sentinel-2-l2a", "N0512")] = {"name": "sentinel-2-l2a",
                                                            "version": "N0512"}
    for band in ["B02", "B03", "B04", "B08"]:
        fake_db.scene_bands.append({"scene_id": scene_id, "band_name": band,
                                    "object_key": f"scenes/{scene_id}/{band}.tif",
                                    "scale_factor": 0.0001})
    job_id = "00000000-0000-4000-8000-0000000009a1"
    fake_db.jobs[job_id] = {
        "id": job_id, "project_id": "p1", "job_type": "reconstruct",
        "mode": "reconstruct", "status": "CLAIMED", "progress": 0.0,
        "requested_by": "u1", "idempotency_key": "k1", "input_fingerprint": "f",
        "config_hash": "c", "model_version_id": model_id,
        "error_code": None, "error_message": None, "created_at": None,
        "started_at": None, "completed_at": None, "priority": 100,
        "attempt": 1, "claim_token": "tok", "lease_expires_at": None}
    for step in ["preprocess", "reconstruct", "uncertainty", "validate", "report"]:
        fake_db.steps[(job_id, step)] = {"status": "QUEUED", "progress": 0.0,
                                         "attempt": 0}
    fake_db.job_inputs.append({"job_id": job_id, "scene_id": scene_id,
                               "role": "input"})
    return {"job_id": job_id, "scene_id": scene_id, "fake_db": fake_db,
            "root": root, "model_id": model_id}


def test_reconstruct_writes_previews_and_run_metadata(reconstruct_env, monkeypatch):
    """The worker's reconstruct job emits all five PRD §11 artifacts."""
    from backend.queue import set_active_claim
    from worker import run as run_mod

    env = reconstruct_env
    job = env["fake_db"].jobs[env["job_id"]]
    set_active_claim(job["id"], "tok")
    try:
        arts = run_mod.run(job)
    finally:
        from backend.queue import discard_active_claim
        discard_active_claim(job["id"])

    types = sorted(a["artifact_type"] for a in
                   env["fake_db"].artifacts.values())
    assert types == ["preview_false_color", "preview_rgb", "run_metadata",
                     "sr_output", "uncertainty"]
    by_type = {a["artifact_type"]: a for a in env["fake_db"].artifacts.values()}
    # PNG previews really exist on disk and are valid images.
    for t, name in (("preview_rgb", "preview_rgb.png"),
                    ("preview_false_color", "preview_false_color.png")):
        p = env["root"] / "previews" / by_type[t]["object_key"]
        assert p.exists(), p
        assert Image.open(p).format == "PNG"
    # run_metadata.json carries the staged scene's provenance.
    mp = env["root"] / "previews" / by_type["run_metadata"]["object_key"]
    meta = json.loads(mp.read_text(encoding="utf-8"))
    assert meta["model"]["name"] == "bicubic_4x"
    prod = meta["inputs"]["products"][0]
    assert prod["provider_product_id"].startswith("S2A_MSIL2A_")
    assert prod["tile_id"] == "T33TTG"
    assert prod["processing_baseline"] == "N0512"
    assert meta["grid"]["grid_m"] == 2.5
    assert meta["runtime"]["runtime_s"] is not None
    # The job completed and every artifact is retrievable through the job view.
    assert job["status"] == "COMPLETED"
    assert len(arts) == 5


def test_reconstruct_media_types_registered(reconstruct_env, monkeypatch):
    from backend.queue import set_active_claim, discard_active_claim
    from worker import run as run_mod

    env = reconstruct_env
    job = env["fake_db"].jobs[env["job_id"]]
    set_active_claim(job["id"], "tok")
    try:
        run_mod.run(job)
    finally:
        discard_active_claim(job["id"])
    by_type = {a["artifact_type"]: a for a in env["fake_db"].artifacts.values()}
    assert by_type["preview_rgb"]["media_type"] == "image/png"
    assert by_type["preview_false_color"]["media_type"] == "image/png"
    assert by_type["run_metadata"]["media_type"] == "application/json"
    assert by_type["sr_output"]["media_type"] == "image/tiff"


def test_typed_artifact_lookup_returns_requested_type(reconstruct_env, monkeypatch):
    """Literal artifact_type filters must not return a sibling artifact row."""
    from backend.queue import set_active_claim, discard_active_claim
    from worker import run as run_mod

    env = reconstruct_env
    job = env["fake_db"].jobs[env["job_id"]]
    set_active_claim(job["id"], "tok")
    try:
        run_mod.run(job)
    finally:
        discard_active_claim(job["id"])

    from backend import db
    row = db.query(
        """
        select object_key from raster_artifacts
        where job_id = %s and artifact_type = 'sr_output' limit 1
        """,
        (env["job_id"],), one=True)
    assert row is not None and "/sr_output/" in row["object_key"]
    row = db.query(
        """
        select object_key from raster_artifacts
        where job_id = %s and artifact_type = 'uncertainty' limit 1
        """,
        (env["job_id"],), one=True)
    assert row is not None and "/uncertainty/" in row["object_key"]
    assert row["object_key"] != row
