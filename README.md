# SIH26142 "Sentry" — Supabase Control Plane Backend

Validation-centered geospatial platform: reconstructs a sub-4 m Sentinel-2 product
(10 m → 2.5 m, B02/B03/B04/B08) and — its primary job — collects evidence and decides
whether that reconstruction is spatially, spectrally, geometrically and observationally
trustworthy. **Inferred detail is never represented as directly observed satellite truth.**

## Architecture

```
Browser / Client
   │
   ├── Supabase Auth (JWT)
   ├── Supabase Realtime (job events)
   └── FastAPI HTTPS
          │
          ├── API / orchestration / signed URLs
          ├── Supabase Postgres + PostGIS   (metadata, jobs, metrics, provenance)
          └── Supabase Storage object references (rasters by object key)
                    │
             Job dispatcher (Postgres claim queue)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   CPU preprocessing     GPU worker pool
   (GDAL/Rasterio)      (SR inference, uncertainty)
          │                   │
          └─────────┬─────────┘
                    ▼
           Validation Engine
             (components A–G, PASS/CAUTION/FAIL)
                    │
          report + metrics + uncertainty
                    ▼
        Supabase Postgres / Storage
```

## Quickstart

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

# local Supabase via CLI (or point .env at a managed project)
supabase start && supabase db reset

# API
uvicorn backend.main:app --reload

# worker (CPU preprocess / reconstruct / validate loop)
python -m worker.main

# standalone science-pipeline smoke test (no Supabase required)
python scripts/smoke_e2e.py
```

## Environment variables

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL (public config) |
| `SUPABASE_ANON_KEY` | Anon/publishable key (client-visible per Supabase architecture) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service key — **server-side only** (FastAPI/workers) |
| `SUPABASE_DB_URL` | Postgres connection string for workers/API (service-level) |
| `VALIDATION_PROTOCOL_VERSION` | Default `sih26142_v1`; stamped on every validation run |
| `WORKER_CONCURRENCY` | Max concurrent jobs per worker process |
| `MAX_TILE_PIXELS` | Cap on tile pixel budget per job |
| `ARTIFACT_ROOT` | Local artifact cache root (default `./data/artifacts`) |
| `DEV_AUTH` | Explicit local-only `X-Dev-User` support; default `false` |
| `CORS_ORIGINS` | Comma-separated frontend origin allowlist; empty disables CORS |
| `CODE_COMMIT` | Immutable source revision stamped in provenance |
| `WORKER_IMAGE` | Immutable worker image digest stamped in provenance |

## Error model

`INVALID_AOI` `SCENE_NOT_FOUND` `DATA_CORRUPT` `MODEL_UNAVAILABLE` `GPU_OOM`
`VALIDATION_INCOMPLETE` `ARTIFACT_WRITE_FAILED` `AUTH_FORBIDDEN` `JOB_CONFLICT` —
returned as `{"error": {"code": ..., "message": ...}}`.

## Job lifecycle

`QUEUED → CLAIMED → PREPROCESSING → RECONSTRUCTING → UNCERTAINTY → VALIDATING → REPORTING → COMPLETED`
(terminal `FAILED` / `CANCELLED`). Every transition writes `jobs` + `job_steps` rows;
Realtime streams permitted changes to clients. Progress is approximate and never
scientific evidence.
