# SENTRY — Sentinel-2 Super-Resolution with Validation

SENTRY super-resolves Sentinel-2 imagery from 10 m to 2.5 m per pixel (bands B02, B03, B04, B08),
then checks whether the result is trustworthy **before anyone is allowed to use it**.
Model-generated detail is never presented as new observation — the validation step is the point.

Built for Smart India Hackathon problem statement SIH26142 (NTRO, Space Technology).

![SUBPIXEL-SENTRY operator console](assets/console_split_slider.png)

## Run it (Windows, one click)

Double-click **`Start-SENTRY.bat`**. It boots Postgres, the API and the console,
then opens the console in your browser. `Stop-SENTRY.bat` shuts the servers down.

| Service | Address |
|---|---|
| Console | http://127.0.0.1:8080/index.html?backend=http://127.0.0.1:8077 |
| API + docs | http://127.0.0.1:8077/docs · health at `/v1/health` |
| Postgres | 127.0.0.1:54322 (`sentry-postgres` container) |

First load hard-refresh once (`Ctrl+Shift+R`) so the latest console scripts load.
If the page ever looks stale or points at the wrong backend: **Connect… → Reset saved**.

### Manual start (any OS)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker start sentry-postgres        # or: python scripts/db_init.py --recreate on empty DB
$env:DEV_AUTH="true"; $env:ARTIFACT_STORE="local"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8077
python -m http.server 8080          # different port from the API
python -m worker.main               # job worker (needs the DB)
```

## Using the console

The run bar walks you through four steps — each one is clickable:

1. **Backend** — where the API lives. Found automatically by scanning localhost;
   override with `?backend=` or in **Connect…**.
2. **Identity** — who you are. On a dev backend the console starts a **demo
   session automatically** (user + project, stored in your browser only).
   Turn it off in Connect… → Advanced.
3. **Scene + Model** — pick a staged L2A scene and the reconstruction model.
4. **Run** — submits the job and streams progress, previews and validation.

**Connect…** shows live status (backend / identity / project), a backend finder,
one-click demo session, and manual UUID fields. No backend? Both Run buttons
play an honestly-labeled simulator demo instead of failing.

Map viewport modes: **Split Slider** (10 m vs 2.5 m), **10m**, **2.5m**, and
**3D Tactical DEM** — a Three.js Himalayan terrain model
(`assets/terrain_diffuse/height/normal.jpg`) with relief, contour, auto-orbit
and photo/elevation controls plus fly-to-sector. Pure visualization, never analysis.

## How the pipeline works

```
CDSE catalogue ──search──► product ──download+MD5──► SAFE zip ──► B02/B03/B04/B08
job (QUEUED) ──claim──► preprocess ──► tile (feathered) ──► SR model ──► stitch
    ──► sr.tif (COG, 2.5 m) + uncertainty.tif ──► validation ──► report.json
    ──► PASS / CAUTION / FAIL (FAIL closes the run, never COMPLETED)
```

Models: `bicubic_4x` (baseline), `custom_mf_sr` (multi-frame fusion, 1–8 frames),
`opensr_ldsrs2` (ESA diffusion; needs weights + torch, else `MODEL_UNAVAILABLE`).

Job states: `QUEUED → CLAIMED → PREPROCESSING → RECONSTRUCTING → UNCERTAINTY →
VALIDATING → REPORTING → COMPLETED`, plus `FAILED`/`CANCELLED`. Claims carry a
lease with heartbeat renewal; a reaper requeues stale claims (`FOR UPDATE SKIP LOCKED`).

Validation checks georeferencing, PSNR/SSIM on valid pixels, SAM/ERGAS,
scale-back observation consistency, and uncertainty calibration — any missing
evidence fails the run.

## HTTP API

All routes under `/v1` (docs at `/docs`). Auth: `Authorization: Bearer <Supabase JWT>`,
or `X-Dev-User: <uuid>` when the backend runs with `DEV_AUTH=true` (local only).

| Group | Routes |
|---|---|
| health | `GET /v1/health` |
| projects | `GET/POST /v1/projects` |
| aois | `GET/POST /v1/aois` |
| scenes | `GET /v1/scenes/search` |
| jobs | `GET/POST /v1/jobs`, `GET /v1/jobs/{id}`, `POST /v1/jobs/{id}/cancel` |
| validations | `POST/GET /v1/validations`, `GET /v1/validations/{id}` |
| reports | `GET /v1/reports/{id}` |
| artifacts | `GET /v1/artifacts/{id}/content`, `POST …/signed-url` |
| models | `GET /v1/models`, `GET /v1/models/status` |
| alerts | `GET/POST /v1/alerts`, `POST /v1/alerts/{id}/status` |
| copernicus | `POST /v1/copernicus/search`, `POST /v1/copernicus/ingest` |
| dev | `POST /v1/dev/session` (only with `DEV_AUTH=true`) |

Errors: `{"error": {"code": "STABLE_CODE", "message": "..."}}`.

## Configuration

`.env` (gitignored). Everything below is optional depending on how far you go:

```ini
SUPABASE_DB_URL=postgresql://postgres:...@127.0.0.1:54322/postgres
SUPABASE_URL= / SUPABASE_ANON_KEY= / SUPABASE_SERVICE_ROLE_KEY=
COPERNICUS_USERNAME= / COPERNICUS_PASSWORD=   # product download only; search is anonymous
DEV_AUTH=true                                  # X-Dev-User identity. Local dev only.
ARTIFACT_STORE=local                           # local | storage | auto
ARTIFACT_ROOT=./data/artifacts
JOB_LEASE_SECONDS=300
JOB_MAX_ATTEMPTS=3
```

Database schema: `supabase/migrations/0001..0014` (plus `0003a/b` split) applied in
order — `python scripts/db_init.py` on an empty DB, `--verify` to check,
`supabase db reset` with the Supabase CLI. `supabase/local/*.sql` shims
Supabase-only objects (roles, `auth`/`storage` schemas) for plain Postgres.

## Outputs

Per reconstruct-validate job, under `ARTIFACT_ROOT`:

| File | Contents |
|---|---|
| `sr.tif` | 4-band COG at 2.5 m, original CRS |
| `uncertainty.tif` | Per-pixel uncertainty (gradient proxy, labeled as such) |
| `report.json` | Metrics, decision, protocol version |
| `preview_rgb.png` / `preview_false_color.png` | Visualizations only — analyze `sr.tif` |
| `run_metadata.json` | Provenance: inputs, model, grid, commit, config hash |

## Data sources and licenses

- **Sentinel-2** (Copernicus Data Space): production input, L2A 10 m bands.
- **WorldStrat v1.1** (Zenodo 15382551): reference data. SPOT HR imagery is
  **CC BY-NC 4.0** — outputs trained on it inherit the non-commercial term.
- **OpenSR LDSR-S2** (ESAOpenSR/opensr-model, pinned v1.1.1): reference model.
  Fetch: `python scripts/fetch_opensr_weights.py`. See `SOURCES.md` for hashes/ledger.

## Testing

```powershell
python scripts/compile_check.py   # byte-compile check (skips .venv)
python scripts/smoke_e2e.py       # full pipeline, no DB, no network
python -m pytest -q               # 77 passed, 1 skipped (RLS needs live Postgres)
```

## Repository layout

```
backend/            FastAPI control plane (routers, auth, queue, validation engine)
worker/             claim-execute loop (preprocess, tiling, baselines, COG io)
supabase/migrations 0001..0014 versioned schema (+ RLS, seeds, alerts)
supabase/local      local-only shims for plain Postgres
tests/              pytest suite (hermetic fake_db; RLS self-skips)
scripts/            serve.py, db_init.py, smoke_e2e.py, fetchers, stage_real_scene.py
index.html js/ css/ assets/   operator console (static)
Start-SENTRY.bat / Stop-SENTRY.bat   one-click local run (Windows)
```

## Troubleshooting

- **Page shows nothing / badge says offline** — start everything with
  `Start-SENTRY.bat`, hard-refresh, or Connect… → Reset saved.
- **Demo session fails** — needs Postgres (`docker start sentry-postgres`) and
  `DEV_AUTH=true` on the backend; check `/v1/health` (`db`, `dev_auth`).
- **Scene list empty** — no scenes staged yet. Ingest via
  `POST /v1/copernicus/ingest` (needs CDSE credentials) or
  `python scripts/stage_real_scene.py`.
- **`MODEL_UNAVAILABLE` for opensr_ldsrs2** — fetch weights + install torch, or
  use `bicubic_4x` / `custom_mf_sr`.
- **Port 8000 busy** — the launcher uses 8077/8080; Docker Desktop may hold 8000.

## Known limitations

- Uncertainty raster is a gradient-magnitude proxy, not a diffusion posterior.
- Pixel inspector and evidence dossiers are simulator-backed; alerts/metrics
  charts mix live rows with clearly-labeled demo content where noted.
- No Copernicus frame selector (cloud-rank, 8-frame cap enforced only in worker).
- RLS test runs against live Postgres only; lease mechanics covered by fakes.
