# SIH26142 Sentry — Supabase Control Plane (Database Layer)

Postgres/PostGIS is the source of truth for metadata, geospatial identity, job state,
metrics and provenance. Rasters live in Storage buckets; Postgres stores only their
logical identity (object keys, checksums, dimensions).

## Running locally

```bash
supabase start          # boots local Postgres, Auth, Storage, Realtime (CLI)
supabase db reset       # applies supabase/migrations/* in order, then seed.sql
```

Migrations are applied in numeric order:

| Migration | Contents |
|---|---|
| `0001_extensions.sql` | PostGIS + pgcrypto |
| `0002_core_tables.sql` | 20-table core schema (orgs, projects, AOIs, scenes, jobs, validation, provenance) |
| `0003_compatibility.sql` | Upgrade-safe ownership/queue compatibility columns and fingerprints |
| `0003_indexes.sql` | GiST spatial indexes + btree/composite queue indexes |
| `0004_rls.sql` | RLS policies, helper functions, realtime publication |
| `0005_storage.sql` | 8 private buckets + project-scoped object read policy |
| `0006_seed.sql` | Dataset sources, model registry, demo project, protocol registration |
| `0007_job_retry_index.sql` | Active idempotency index, duplicate preflights, artifact/report constraints |

## Storage buckets

| Bucket | Access |
|---|---|
| `raw-ingest`, `scene-assets`, `model-artifacts` | Private — service-role only (backend/workers) |
| `references`, `sr-outputs`, `uncertainty`, `benchmarks`, `reports` | Project-scoped: members can read objects whose path starts with their `{project_id}/` |

Object naming convention: `{project_id}/{job_id}/{artifact_type}/{artifact_version}/{filename}` —
immutable paths; completed artifact rows always point at immutable objects.

## RLS model

- Membership lives in `project_members` (role hierarchy: `owner > operator > reviewer > viewer`).
- Organization ownership is tracked by the compatibility `created_by` column;
  legacy NULL rows fail closed until explicitly backfilled.
- Row visibility for project-scoped tables resolves through security-definer helpers
  (`has_project_role`, `has_job_project_role`, `has_vr_project_role`) that check the caller's JWT `auth.uid()`.
- Catalog tables (`scenes`, `dataset_sources`, `model_versions`, …) are readable by any
  authenticated user but writable only via the service role (no authenticated write policies exist).
- Job/artifact/validation reads stream to permitted members only; Supabase Realtime respects RLS
  on the `supabase_realtime` publication (`jobs`, `job_steps`, `validation_runs`, `raster_artifacts`).

## Worker connections

Workers and the FastAPI backend connect with the **service-role key / `SUPABASE_DB_URL`** which
bypasses RLS — and therefore **must stay server-side only**. Browsers use the anon key + user JWT;
they can only read rows in projects they belong to. Never put service credentials in client code.

## Migration discipline

All schema changes are versioned migrations committed to Git. Never edit a schema by hand
without a matching migration file. `supabase db reset` must apply cleanly to an empty database —
that is the CI gate.
