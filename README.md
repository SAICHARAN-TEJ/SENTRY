# SENTRY — Sentinel-2 Super-Resolution with Validation

SENTRY super-resolves Sentinel-2 imagery from 10 m to 2.5 m per pixel (bands B02, B03, B04, B08) and then checks whether the result is actually trustworthy before anyone is allowed to use it. The validation step is the point of the project: model-generated detail is not new observation, and the system is built so it can never be presented as such.

This is the codebase for Smart India Hackathon problem statement SIH26142 (NTRO, Space Technology). The product requirements live in the SIH statement and the project PRD; source datasets and their checksums are tracked in [SOURCES.md](SOURCES.md).

![SUBPIXEL-SENTRY Tactical Operator Console: Split Slider Comparison and Sub-Pixel Inspector](assets/console_split_slider.png)
*Figure 1: SUBPIXEL-SENTRY tactical operator console — interactive split-slider comparing native 10 m Sentinel-2 L2A imagery (left) with 2.5 m super-resolved reconstruction (right), alongside the FCLS sub-pixel material abundance inspector (16 sub-pixel cells @ 2.5 m for each 100 m² parent pixel).*

---

## Table of contents

1. [What it does](#what-it-does)
2. [Current status](#current-status)
3. [Operator console & tactical views](#operator-console--tactical-views)
4. [Repository layout](#repository-layout)
5. [How the pipeline works](#how-the-pipeline-works)
6. [The validation engine](#the-validation-engine)
7. [Tactical alerts & target intelligence](#tactical-alerts--target-intelligence)
8. [Requirements](#requirements)
9. [Setup](#setup)
10. [Running things](#running-things)
11. [Configuration reference](#configuration-reference)
12. [HTTP API](#http-api)
13. [Outputs and file formats](#outputs-and-file-formats)
14. [Fetching source data](#fetching-source-data)
15. [Data sources and licenses](#data-sources-and-licenses)
16. [Known limitations](#known-limitations)
17. [Testing](#testing)
18. [Troubleshooting](#troubleshooting)

---

## What it does

A job takes one or more co-registered Sentinel-2 L2A scenes (the four native 10 m bands), runs a super-resolution model to produce a 2.5 m 4-band Cloud-Optimized GeoTIFF plus a per-pixel uncertainty raster, and then runs a mandatory validation pass before writing a report.

Three model paths exist:

| Model | What it is | Status |
|---|---|---|
| `bicubic_4x` | Plain bicubic interpolation, 4x. The no-learning lower bound. | Works |
| `opensr_ldsrs2` | ESA's OpenSR LDSR-S2 latent diffusion model (10 m → 2.5 m RGB-NIR with uncertainty). | Wired in the registry; needs weights and PyTorch installed. Raises `MODEL_UNAVAILABLE` without them. |
| `custom_mf_sr` | The project's own multi-frame fusion heuristic. Deterministic, needs no GPU, works with 1–8 frames. | Works |

The multi-frame path accepts between 1 and 8 temporal frames of the same tile. There is no hard cap enforced yet; the PRD's frame selector (rank revisits by cloud cover, pick at most 8) is not implemented.

The frontend in `index.html` is an operator console with a real backend client: job submission, live job tracking (polling to terminal state), validations, reports, artifact signing, projects, scenes, models and the Copernicus connector all go through `js/api.js` against `/v1` routes with Bearer or dev-header auth. The alerts table, pixel inspector and evidence dossiers remain simulator-backed until a backend alerts domain exists (those methods are marked SIMULATED in `js/api.js`).

---

## Current status

Working today, verified by the test suite:

- Job queue with `FOR UPDATE SKIP LOCKED` claiming, idempotency keys, cancellation, and crash-safe claims: every claim carries a lease (heartbeat-renewed) and a fencing token, and a reaper requeues or fails abandoned jobs.
- Copernicus Data Space catalogue search (anonymous) and product download (authenticated, fail-closed without credentials), with MD5 verification against the catalogue before anything is staged.
- SAFE zip band extraction for both legacy (`_B02.jp2`) and current (`_B02_10m.jp2`) naming layouts, grid cross-checks across bands.
- Preprocessing, feathered tiling with partition-of-unity stitching, bicubic and multi-frame reconstruction, COG writing with preserved CRS/transform.
- Validation: PSNR/SSIM on valid pixels only, SAM, ERGAS, RMSE, scale-back consistency against the original 10 m observation, uncertainty calibration when a reference exists, PASS/CAUTION/FAIL decision that fails closed on missing data.
- A full offline smoke test (`scripts/smoke_e2e.py`) that needs no database and no network.

Not done yet, in rough priority order:

- No Copernicus-connector-driven frame selector, no bootstrap confidence intervals in benchmarks, no LPIPS.
- RLS policies are written but the RLS test only runs against a real Postgres.

---

## Operator console & tactical views

The operator interface (`index.html`) provides high-fidelity situational awareness and analytical tooling across several dedicated modes:

### 1. 2D Sub-Pixel Split Slider & Material Inspector
Allows analysts to swipe dynamically between native 10 m Sentinel-2 L2A reflectance and the reconstructed 2.5 m super-resolved raster. Clicking any pixel activates the **FCLS Pixel Inspector**, rendering a 16-cell sub-pixel breakdown (4×4 grid at 2.5 m resolution within the 100 m² parent cell) along with Fully Constrained Least Squares abundance percentages across Impervious, Vegetation, Water, Soil, and Shade endmembers.

### 2. 3D Tactical DEM Viewport
Operators can switch into real-time 3D terrain elevation mode rendered via Three.js. This projects satellite textures over high-resolution Digital Elevation Models (DEM), allowing terrain-aware inspection of ridgelines, valleys, and forward deployment lines.

![SUBPIXEL-SENTRY 3D Tactical DEM Viewport](assets/console_3d_dem.png)
*Figure 2: Real-time 3D Tactical Digital Elevation Model (DEM) terrain viewport rendered via Three.js with AOI bounding over forward deployment areas (Sector Tawang — LAC Forward Area).*

---

## Repository layout

```
SENTRY/
├── backend/                  FastAPI control plane
│   ├── main.py               App entry, router wiring
│   ├── config.py             Settings, loaded from environment / .env
│   ├── db.py                 psycopg pool, transactions
│   ├── auth.py               Supabase JWT validation, dev header, role checks
│   ├── errors.py             Stable error codes -> HTTP status mapping
│   ├── schemas.py            Pydantic request/response models
│   ├── queue.py              Job claims (SKIP LOCKED), lease/heartbeat, reaper
│   ├── ingest.py             Scene/band registration
│   ├── supabase_client.py    Auth + storage REST helpers
│   ├── copernicus.py         CDSE catalogue search, download, SAFE extraction
│   ├── routers/              projects, aois, scenes, jobs, validations,
│   │                         reports, artifacts, models, copernicus
│   └── validation/           engine.py (metrics + decision), runner.py (persistence)
├── worker/                   Claim-execute loop
│   ├── main.py               Process entry: claim -> run -> repeat
│   ├── run.py                Job execution, artifact store, step transitions
│   ├── preprocess.py         Reflectance scaling, validity masks
│   ├── tiling.py             Overlapping tiles, feather weights, stitching
│   ├── baselines.py          bicubic, custom multi-frame, uncertainty proxy
│   ├── registry.py           Model registry; blocks visual-only models
│   └── rasterio_io.py        COG read/write, sha256
├── supabase/
│   ├── migrations/           0001..0009: PostGIS, tables, RLS, storage, seeds, lease, output schema
│   └── config.toml           Supabase CLI project config
├── tests/                    pytest suite (offline; RLS test self-skips)
├── scripts/
│   ├── smoke_e2e.py          End-to-end pipeline without a database
│   ├── compile_check.py      Byte-compiles every .py; fails on syntax errors
│   ├── fetch_sources.py      WorldStrat v1.1 downloader, MD5-verified, resumable
│   ├── fetch_opensr_weights.py   LDSR-S2 checkpoint, SHA-256 recorded
│   ├── fetch_sentinel2_product.py Single S2 product, verified against catalogue MD5
│   └── make_fixtures.py      Synthetic scene fixtures for tests
├── index.html, js/, css/, assets/   Operator console (static, simulator-backed)
├── fixtures/output/          Generated test rasters (gitignored)
├── data/                     Datasets, checkpoints, artifacts (gitignored)
├── SOURCES.md                Source lock: datasets, hashes, fetch ledger
├── docker-compose.yml        api + worker containers (DB comes from Supabase)
└── Dockerfile
```

---

## How the pipeline works

```
  CDSE catalogue ──search──► pick product ──download+MD5 check──► SAFE zip
                                                                       │
                                                        extract B02/B03/B04/B08
                                                                       ▼
                                                            scenes + scene_bands
                                                                       ▼
  job (QUEUED) ──claim──► worker: preprocess ──► tile (feathered) ──► SR model
                                                                       ▼
                                              stitch tiles ──► sr.tif (COG, 2.5 m)
                                                       + uncertainty.tif
                                                                       ▼
                                              validation engine ──► report.json
                                                       PASS / CAUTION / FAIL
                                                                       ▼
                                     artifacts registered in Postgres, uploaded
                                     to Storage when configured
```

Job status moves through `QUEUED → CLAIMED → PREPROCESSING → RECONSTRUCTING → UNCERTAINTY → VALIDATING → REPORTING → COMPLETED`, with `FAILED` and `CANCELLED` as terminal states. Each transition writes a `job_steps` row. A job whose validation cannot complete is marked `FAILED`, never `COMPLETED`.

The worker claims jobs from a Postgres queue using `SELECT ... FOR UPDATE SKIP LOCKED`, so multiple workers can run against the same database without double-processing. Resubmitting a job with the same idempotency key while one is active returns the existing job instead of duplicating work.

### End-to-end telemetry and cryptographic audit trail

Every execution stage produces machine-verifiable telemetry stored as structured JSON and stamped with cryptographic SHA-256 digests. This guarantees forensic auditability for intelligence workflows.

![SUBPIXEL-SENTRY Pipeline Stage Artifact Telemetry (04 TRACE)](assets/console_trace.png)
*Figure 3: End-to-end pipeline trace telemetry and stage verification log (Stages 00–04) showing SHA-256 artifact hashing (`e3b0c442...991b7852`), operations breakdown, and human-in-the-loop audit overrides.*

---

## The validation engine

Every reconstruct-validate job runs these checks before its report exists:

1. **Georeferencing** — the SR product must sit exactly on the expected 2.5 m grid derived from the 10 m input transform (scale by 4, same CRS).
2. **Spatial fidelity** — PSNR and SSIM computed on valid pixels only; nodata is excluded, and SSIM windows eroded at mask edges.
3. **Spectral fidelity** — SAM (spectral angle) and ERGAS, computed norm-invariantly so band scaling conventions cannot flatter the model.
4. **Observation consistency** — the 2.5 m output is reduced back to 10 m with a fixed, documented operator and compared to the original observation. A model that "invents" content inconsistent with the measurement fails here.
5. **Uncertainty calibration** — when a reference dataset exists, uncertainty deciles are checked against actual residuals. Uncertainty that does not correlate with error is reported.
6. **Decision** — PASS, CAUTION, or FAIL per configured thresholds (see `backend/validation/engine.py` for the current numbers). Any NaN in the evidence counts as missing evidence, and missing evidence fails the run.

The uncertainty raster currently comes from a gradient-magnitude proxy, not from diffusion sampling. It is labeled as a proxy everywhere it appears. Replacing it with OpenSR's native per-pixel uncertainty is planned.

### Scientific verification & metrics telemetry

Validation results are synthesized into rigorous quantitative metrics to prevent hallucinated artifacts from contaminating downstream intelligence:

![SUBPIXEL-SENTRY Scientific Verification & Metrics Dashboard (03 METRICS)](assets/console_metrics.png)
*Figure 4: Scientific verification dashboard: 4-term loss convergence (L1 Cross-Entropy, L2 Abundance, L3 Spatial, L4 Mass Conservation), controlled injection sensitivity testing (~45 m² inflection threshold), monotonic confidence calibration reliability diagram, and cross-scale generalization stress test.*

- **4-Term Loss Convergence**: Balances spatial resolution against mass conservation and spectral unmixing constraints, ensuring no degenerate compromise.
- **Controlled Injection Sensitivity**: Calibrates the exact target detection boundary (~45 m² inflection point for synthetic targets, 100–150 m² under real-world atmospheric noise).
- **Confidence Calibration (Reliability Diagram)**: Enforces monotonic precision so reported model confidence matches empirical truth.
- **Cross-Scale Stress Test**: Verifies reconstruction integrity against held-out 20 m → 5 m degraded reference bands.

---

## Tactical alerts & target intelligence

When super-resolution and unmixing detect localized changes in surface composition, candidates are registered into the Tactical Alerts queue.

![SUBPIXEL-SENTRY Tactical Alerts & Target Queue (02 ALERTS)](assets/console_alerts.png)
*Figure 5: Tactical target detection queue displaying georeferenced alert coordinates, UTM grid coordinates, sub-pixel impervious material deltas, automated classification (structures, access roads, helipads, quay walls), confidence scores, and human audit status.*

- **Sub-Pixel Material Delta**: Detects sub-10 m structural changes (e.g., `+18.7% Impervious (+75 m²)`) even when the overall 10 m pixel appears unchanged.
- **Classification Engine**: Labels detections using geometric rules and spectral signatures (`PROBABLE STRUCTURE`, `PROBABLE ACCESS ROAD`, `BORDER DISCREPANCY`, `REINFORCED HELIPAD`, `SENTRY TOWER FOOTING`).
- **Human-in-the-Loop Audit**: Alerts can be placed in `REVIEW`, `CONFIRMED`, or `DISMISSED` state with full operator provenance logged in the audit ledger.
- **Evidence Dossier**: Every alert links directly to underlying raster crops, spectral plots, and signed COG download URLs.

---

## Requirements

- Python 3.10 or newer (3.11/3.12 recommended). Uses `X | Y` type syntax.
- Windows, Linux, or macOS. On Windows, `pip install rasterio` pulls a wheel with bundled GDAL; no system GDAL needed.
- A Postgres with PostGIS for the full stack. Three options, easiest first:
  1. None at all — the smoke test and most tests run without a database.
  2. Local Supabase via the Supabase CLI (`supabase start`).
  3. Any Postgres 15+ with the `postgis`, `pgcrypto` extensions.
- PyTorch + OpenSR weights only if you want the `opensr_ldsrs2` model. Not in `requirements.txt`; everything else runs without them.
- Git LFS is not used. Large data lives under `data/` (gitignored).

---

## Setup

```powershell
# from the repo root (Windows PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the template below into `.env` (the file is gitignored) and fill in what you have. Everything is optional depending on how far you want to go:

```ini
# --- Supabase / Postgres (required for API + worker against a real DB) ---
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_DB_URL=postgresql://user:pass@localhost:5432/postgres

# --- Copernicus product download (catalogue search needs nothing) ---
COPERNICUS_USERNAME=you@example.com
COPERNICUS_PASSWORD=...

# --- Local development only ---
DEV_AUTH=false          # true lets the X-Dev-User header act as identity. Never in prod.
CORS_ORIGINS=           # comma-separated origins; empty disables CORS middleware

# --- Tuning (defaults are sensible) ---
ARTIFACT_ROOT=./data/artifacts
WORKER_CONCURRENCY=1
MAX_TILE_PIXELS=4194304
VALIDATION_PROTOCOL_VERSION=sih26142_v1
JOB_LEASE_SECONDS=300    # claim lease; heartbeat renews at lease/3
JOB_MAX_ATTEMPTS=3       # reaper requeues until this, then fails LEASE_LOST

# --- Provenance stamping ---
CODE_COMMIT=
WORKER_IMAGE=
```

Database schema: apply `supabase/migrations/*.sql` in filename order with any migration tool, or run `supabase db reset` if you use the Supabase CLI.

### Frontend

`index.html` is static. Serve it from any port **except** 8000 (the API's default port):

```bash
python -m http.server 8080
# then open http://localhost:8080
```

It degrades gracefully without network access: self-hosted fonts, a Three.js load timeout with a 2D fallback, reduced-motion support. As noted above, it runs on its built-in simulator; it does not yet call this backend.

---

## Running things

All commands from the repo root with the venv active.

```bash
# Verify everything compiles
python scripts/compile_check.py

# Full pipeline smoke test: preprocess -> tile -> reconstruct -> stitch ->
# COG round-trip -> validation -> report. No DB, no network needed.
python scripts/smoke_e2e.py

# API server (http://localhost:8000, docs at /docs)
uvicorn backend.main:app --reload

# Worker loop (claims and executes jobs; heartbeat-renewed lease per claim)
python -m worker.main

# Cron-friendly stale-claim sweep (usually unnecessary: idle workers reap)
python -m worker.main --reap-stale

# Test suite
python -m pytest -q

# Docker: API + CPU worker (expects a reachable Supabase/Postgres via .env)
docker compose up --build
```

---

## Configuration reference

Set via environment variables or `.env` (pydantic-settings, `env_file=".env"`).

| Variable | Default | Purpose |
|---|---|---|
| `SUPABASE_URL` | empty | Supabase project URL; enables Storage uploads when combined with the service key |
| `SUPABASE_ANON_KEY` | empty | Anon key for JWT verification against Supabase Auth |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | Server-side only. Never expose to clients |
| `SUPABASE_DB_URL` | empty | Postgres DSN. Empty means "no DB": API refuses DB calls, `LocalSession` is test-only |
| `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD` | empty | CDSE account for product **download**. Search stays anonymous |
| `DEV_AUTH` | `false` | Accept `X-Dev-User` header as identity. Local development only |
| `CORS_ORIGINS` | empty | Comma-separated origin allowlist; empty disables the CORS middleware |
| `ARTIFACT_ROOT` | `./data/artifacts` | Local root for staged scenes and job artifacts |
| `WORKER_CONCURRENCY` | `1` | Concurrent jobs per worker process |
| `MAX_TILE_PIXELS` | `4194304` | Tile pixel budget per job |
| `VALIDATION_PROTOCOL_VERSION` | `sih26142_v1` | Stamped on every validation run and report |
| `JOB_LEASE_SECONDS` | `300` | Claim lease duration. A worker heartbeat renews it at lease/3; a claim whose lease lapses is stale and gets reaped |
| `JOB_MAX_ATTEMPTS` | `3` | Requeue budget for reaped claims; beyond this the job fails permanently with `LEASE_LOST` |
| `CODE_COMMIT` | empty | Git revision stamped into provenance records |
| `WORKER_IMAGE` | empty | Worker image digest stamped into provenance records |

---

## HTTP API

All routes are under `/v1`. Interactive docs at `/docs` when the server runs.

| Group | What it covers |
|---|---|
| `/v1/projects` | Project CRUD, membership, roles (`owner`, `operator`, `viewer`) |
| `/v1/aois` | Areas of interest as WKT polygons, per project |
| `/v1/scenes` | Scene registry and band listing |
| `/v1/jobs` | Submit (with idempotency key), list, cancel, step status |
| `/v1/validations` | Validation runs and metric rows |
| `/v1/reports` | Validation report retrieval |
| `/v1/artifacts` | Artifact metadata, short-lived signed download URLs |
| `/v1/models` | Registered model versions and checksums |
| `/v1/copernicus/search` | Anonymous catalogue search for L2A products over an AOI, with date and cloud-cover filters. Any project role |
| `/v1/copernicus/ingest` | Search + download + verify (catalogue MD5) + extract bands + register the scene. Owner/operator only. Idempotent per product |

Errors always come back as:

```json
{"error": {"code": "STABLE_CODE", "message": "human-readable detail"}}
```

Stable codes: `INVALID_AOI`, `SCENE_NOT_FOUND`, `DATA_CORRUPT`, `MODEL_UNAVAILABLE`, `GPU_OOM`, `VALIDATION_INCOMPLETE`, `ARTIFACT_WRITE_FAILED`, `AUTH_FORBIDDEN`, `JOB_CONFLICT`, `NOT_FOUND`, `QUALITY_FAIL`, `LEASE_LOST`.

Authentication: `Authorization: Bearer <Supabase JWT>` in production. In local development with `DEV_AUTH=true`, an `X-Dev-User: <user-id>` header is accepted instead.

---

## Outputs and file formats

Per reconstruct-validate job, under `ARTIFACT_ROOT`:

| File | Format | Contents |
|---|---|---|
| `sr.tif` | Cloud-Optimized GeoTIFF | 4 bands (B02, B03, B04, B08) at 2.5 m, original CRS, transform divided by 4 |
| `uncertainty.tif` | COG | Per-pixel uncertainty on the same grid (currently gradient-magnitude proxy) |
| `report.json` | JSON | Metrics, decision, protocol version, evidence references |
| `preview_rgb.png` | PNG | True-color (B04/B03/B02) **visualization** of the SR output with a "model-inferred detail" caption; fixed 2–98% stretch over valid pixels |
| `preview_false_color.png` | PNG | False-color (NIR/R/G = B08/B04/B03) **visualization**, same stretch and labeling |
| `run_metadata.json` | JSON | Traceability: input product IDs + sensing times, tile/baseline, model + version, CRS/grid, code commit, config hash, device, runtime |
| `tiles.npz` | npz | Preprocessed reflectance + validity + provenance fingerprint |
| `manifest.json` | JSON | Tile counts, grid, fingerprint, frame count |

Inputs staged from Copernicus keep their provenance: product name, tile id, sensing time, processing baseline (e.g. `N0512`) recorded as the dataset source version, and per-band JP2 files on disk.

---

## Fetching source data

All downloaders verify checksums before accepting a file and keep a `.part` file so an interrupted transfer resumes instead of restarting.

```bash
# WorldStrat v1.1 (training/reference dataset, ~62 GiB for the required set)
python scripts/fetch_sources.py                 # required files
python scripts/fetch_sources.py --with-optional # + L1C and raw HR archives
python scripts/fetch_sources.py --verify-only   # re-check MD5s, download nothing

# OpenSR LDSR-S2 checkpoint (pinned by opensr-model v1.1.1), ~1.1 GiB
python scripts/fetch_opensr_weights.py          # prints the SHA-256 for provenance

# One Sentinel-2 product via the CDSE API (needs COPERNICUS_* in .env)
python scripts/fetch_sentinel2_product.py --from data/target_product.json
# or: --product-id <guid> --md5 <expected-md5>
```

Lands in `data/worldstrat/`, `data/opensr/`, and `data/copernicus/` respectively. Manifests, hashes, and the fetch ledger live in [SOURCES.md](SOURCES.md).

---

## Data sources and licenses

- **Sentinel-2** (Copernicus Data Space Ecosystem): production input. L2A surface reflectance, bands B02/B03/B04/B08 at 10 m.
- **WorldStrat v1.1** (Zenodo record 15382551): paired training/reference data. High-resolution Airbus SPOT imagery is **CC BY-NC 4.0** — non-commercial only. Sentinel-2 layers and labels are CC BY 4.0; the WorldStrat code is BSD-3. Outputs trained on WorldStrat HR data inherit the non-commercial restriction; do not claim unrestricted commercial deployment.
- **OpenSR LDSR-S2** (ESAOpenSR/opensr-model, pinned v1.1.1): reference model and baseline. Cloned into `third_party/` (gitignored) at the pinned tag; checkpoint SHA-256 recorded in SOURCES.md.
- The SPOT "high-resolution reference" is itself pansharpened, not a raw 1.5 m multispectral observation. Validation reports must state this when comparing against it.

---

## Known limitations

Honest list, so nobody has to discover these the hard way:

1. **Frontend integration is partial.** `js/api.js` speaks the real `/v1` API (jobs with live polling, validations, reports, artifacts, Copernicus) and shows a live/simulator badge; but Run Pipeline needs `SentryAPI.setToken(<jwt>)` or `setDevUser(<uuid>)` plus `setProjectId(...)` configured from the browser, and the alerts/pixel-inspector/dossier screens are still simulated — the backend has no alerts domain.
2. **RLS is untested in CI.** `tests/test_rls.py` needs a live Postgres and self-skips otherwise; the policies in migration `0004_rls.sql` have not been exercised against real roles.
3. **Uncertainty is a proxy**, not a probabilistic posterior. Labeled as such, but the PRD's diffusion-sampling uncertainty is not implemented.
4. **No frame selector.** The worker consumes whatever scenes a job references; nothing ranks revisits by cloud cover or caps frames at 8.
5. **Benchmark is thin.** Scores one tile against the downsampled observation with PSNR/SSIM/RMSE only. No SAM/ERGAS, no held-out AOI set, no bootstrap confidence intervals yet.
6. **Metric rows flatten caution.** Per-metric `pass` flags in persisted validation rows mean "run was not FAIL", so an individual metric can be recorded as passing while the overall decision is CAUTION.
7. **Lease mechanics are untested against real Postgres.** Migration `0008_job_lease.sql` and the reaper's `SKIP LOCKED` transaction are covered by the FakeDB test double; concurrency behavior under live Postgres (two workers racing a requeue) has not been exercised yet.
8. **Previews stretch, they do not calibrate.** `preview_rgb.png`/`preview_false_color.png` use a fixed robust percentile stretch for viewing; they are visualizations, never data products — analyze `sr.tif`, not the PNGs.

---

## Testing

```bash
python -m pytest -q          # currently 77 passed, 1 skipped
```

The skip is `test_rls.py`, which needs a live Postgres. Everything else is offline and deterministic: fixtures are synthetic rasters, HTTP calls to CDSE are monkeypatched, and the smoke test exercises the real pipeline code paths end-to-end without a database.

---

## Troubleshooting

**`Copernicus catalogue returned HTTP 403`** — the catalogue rejects requests with default scripting-library User-Agents. The connector already sends an identifying UA; if you wrote your own client, set one.

**Cloud-cover filter returns HTTP 400** — server-side `Attributes/any(...)` filters were rejected by the catalogue as of 2026-09-12. The connector expands Attributes and filters `cloudCover` client-side instead.

**`SAFE zip missing 10m bands`** — check the product actually contains `GRANULE/*/IMG_DATA/R10m/`. Both `_B02.jp2` and `_B02_10m.jp2` namings are handled; R20m copies never satisfy the gate.

**`MODEL_UNAVAILABLE` for opensr_ldsrs2** — weights/PyTorch not installed. Fetch the checkpoint with `scripts/fetch_opensr_weights.py`, install `opensr-model` from the pinned clone, or use `bicubic_4x` / `custom_mf_sr`.

**`database not configured`** — `SUPABASE_DB_URL` is empty. That is correct behavior for smoke tests; set the DSN for API/worker use.

**Job fails with `GPU_OOM`** — worker mapped an out-of-memory error. Lower `MAX_TILE_PIXELS` or run on smaller AOIs.

**Ports collide** — API defaults to 8000. Serve the frontend on any other port (see [Frontend](#frontend)).
