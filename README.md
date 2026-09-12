# SIH26142 "Sentry" — Tactical Land-Cover Intelligence & Validation-Centered Geospatial Platform

Validation-centered geospatial platform & tactical intelligence console: reconstructs a sub-4 m Sentinel-2 product (10 m → 2.5 m, B02/B03/B04/B08) and — its primary job — collects evidence and decides whether that reconstruction is spatially, spectrally, geometrically and observationally trustworthy. **Inferred detail is never represented as directly observed satellite truth.**

---

## System Overview

Sentry combines an immersive tactical front-end console with a robust Supabase control plane, high-throughput worker pool, and rigorous validation engine.

- **Frontend Console**: Tactical Land-Cover Intelligence 3D/2D operator console built with Three.js, interactive map layers, metrics charts, and live job tracking.
- **Control Plane Backend**: FastAPI orchestrator with Supabase Auth, Realtime event streaming, and PostGIS-backed geospatial queries.
- **Processing Workers**: CPU preprocessing (GDAL/Rasterio) and GPU worker pool for super-resolution reconstruction and uncertainty estimation.
- **Validation Engine**: Independent verification suite checking spectral fidelity, edge preservation, hallucination resistance, and radiometric consistency before marking reconstructions as trustworthy.

---

## Architecture

```
Browser / Client (Tactical Console: Three.js / Leaflet / Metrics)
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

---

## Project Structure

```
SENTRY/
├── index.html                   # Tactical Land-Cover Intelligence Console
├── css/                         # Console styling & SpaceX dark theme
├── js/                          # Frontend scripts (Three.js, API, charts, simulation)
├── assets/                      # Textures, terrain maps, fonts, and screenshots
├── backend/                     # FastAPI control plane & validation engine
│   ├── main.py                  # API entry point & lifecycle
│   ├── config.py                # Environment & configuration
│   ├── db.py                    # Database connection pool
│   ├── auth.py                  # JWT validation & role enforcement
│   ├── routers/                 # Endpoints: AOIs, jobs, scenes, reports, artifacts
│   └── validation/              # Verification & evidence engine
├── worker/                      # Processing pipeline & worker pool
│   ├── main.py                  # Worker process loop
│   ├── preprocess.py            # GDAL/Rasterio CPU preprocessing
│   ├── baselines.py             # Bicubic & interpolation baselines
│   └── tiling.py                # Tiling & stride handling
├── supabase/                    # Supabase schema & migrations
│   └── migrations/              # SQL migrations (PostGIS, RLS, storage, seeds)
├── tests/                       # Pytest test suite (API, validation, RLS, tiling)
├── scripts/                     # Smoke tests & compilation utilities
├── docker-compose.yml           # Multi-container local deployment
└── Dockerfile                   # Worker & API container build
```

---

## Quickstart

### Frontend Console
Open `index.html` in your web browser or serve it with any local static server:
```bash
python -m http.server 8000
```
Then navigate to `http://localhost:8000`.

### Backend & Worker Setup
```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

# Local Supabase via CLI (or point .env at a managed project)
supabase start && supabase db reset

# API Server
uvicorn backend.main:app --reload

# Worker Loop
python -m worker.main

# Standalone science-pipeline smoke test (no Supabase required)
python scripts/smoke_e2e.py
```

---

## Environment Variables

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

---

## Error Model

`INVALID_AOI` `SCENE_NOT_FOUND` `DATA_CORRUPT` `MODEL_UNAVAILABLE` `GPU_OOM`
`VALIDATION_INCOMPLETE` `ARTIFACT_WRITE_FAILED` `AUTH_FORBIDDEN` `JOB_CONFLICT` —
returned as `{"error": {"code": ..., "message": ...}}`.

---

## Job Lifecycle

`QUEUED → CLAIMED → PREPROCESSING → RECONSTRUCTING → UNCERTAINTY → VALIDATING → REPORTING → COMPLETED`
(terminal `FAILED` / `CANCELLED`). Every transition writes `jobs` + `job_steps` rows;
Realtime streams permitted changes to clients. Progress is approximate and never
scientific evidence.
