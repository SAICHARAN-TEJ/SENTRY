-- 0002_core_tables.sql
-- SIH26142 "Sentry" - core relational schema.
-- Depends on: 0001_extensions.sql (postgis for geometry, pgcrypto for gen_random_uuid()).

-- ---------------------------------------------------------------------------
-- Organizations / projects / membership
-- ---------------------------------------------------------------------------

create table organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

create table projects (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    name text not null,
    default_crs text not null default 'EPSG:4326',
    settings jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table project_members (
    project_id uuid not null references projects(id) on delete cascade,
    user_id uuid not null,
    role text not null check (role in ('owner', 'operator', 'reviewer', 'viewer')),
    created_at timestamptz not null default now(),
    primary key (project_id, user_id)
);

-- ---------------------------------------------------------------------------
-- Areas of interest
-- ---------------------------------------------------------------------------

create table aois (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    name text not null,
    geom geometry(MultiPolygon,4326) not null,
    bbox jsonb,
    area_m2 double precision,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Dataset sources / scenes / scene bands / reference assets
-- ---------------------------------------------------------------------------

create table dataset_sources (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    version text not null,
    source_type text,
    provider text,
    license text,
    uri text,
    sha256 text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (name, version)
);

create table scenes (
    id uuid primary key default gen_random_uuid(),
    dataset_source_id uuid not null references dataset_sources(id),
    provider_product_id text not null,
    sensing_time timestamptz,
    ingest_status text not null default 'pending'
        check (ingest_status in ('pending', 'staged', 'ready', 'failed')),
    crs text,
    resolution_m double precision,
    footprint geometry(Polygon,4326),
    cloud_pct double precision,
    metadata jsonb not null default '{}'::jsonb,
    object_prefix text,
    created_at timestamptz not null default now(),
    unique (dataset_source_id, provider_product_id)
);

create table scene_bands (
    id uuid primary key default gen_random_uuid(),
    scene_id uuid not null references scenes(id) on delete cascade,
    band_name text not null check (band_name in ('B02', 'B03', 'B04', 'B08')),
    native_resolution_m double precision not null default 10.0,
    object_key text,
    nodata double precision,
    scale_factor double precision default 0.0001,
    dtype text default 'uint16'
);

create table reference_assets (
    id uuid primary key default gen_random_uuid(),
    dataset_source_id uuid not null references dataset_sources(id),
    scene_id uuid references scenes(id),
    footprint geometry(Polygon,4326),
    resolution_m double precision not null,
    spectral_definition jsonb,
    object_key text,
    license text,
    metadata jsonb not null default '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Processing configs / model registry
-- ---------------------------------------------------------------------------

create table processing_configs (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    name text not null,
    config_jsonb jsonb not null,
    config_hash text not null,
    created_at timestamptz not null default now()
);

create table model_versions (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    version text not null,
    framework text,
    checkpoint_object_key text,
    checksum text,
    model_card jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (name, version)
);

-- ---------------------------------------------------------------------------
-- Jobs / job steps / job inputs
-- ---------------------------------------------------------------------------

create table jobs (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    job_type text not null
        check (job_type in ('preprocess', 'reconstruct', 'validate', 'benchmark')),
    mode text not null default 'reconstruct_validate'
        constraint jobs_mode_check
        check (mode in ('preprocess', 'reconstruct', 'reconstruct_validate', 'validate', 'benchmark')),
    status text not null default 'QUEUED'
        check (status in ('QUEUED', 'CLAIMED', 'PREPROCESSING', 'RECONSTRUCTING',
                          'UNCERTAINTY', 'VALIDATING', 'REPORTING', 'COMPLETED',
                          'FAILED', 'CANCELLED')),
    priority int not null default 100,
    progress double precision not null default 0
        check (progress >= 0 and progress <= 1),
    requested_by uuid,
    idempotency_key text not null,
    input_fingerprint text,
    config_hash text,
    model_version_id uuid references model_versions(id),
    error_code text,
    error_message text,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    constraint jobs_project_id_idempotency_key_key unique (project_id, idempotency_key)
);

create table job_steps (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    step_name text not null
        check (step_name in ('preprocess', 'reconstruct', 'uncertainty', 'validate', 'report')),
    status text not null default 'QUEUED'
        check (status in ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED', 'CANCELLED')),
    attempt int not null default 0,
    progress double precision not null default 0,
    started_at timestamptz,
    completed_at timestamptz,
    metrics jsonb,
    unique (job_id, step_name)
);

create table job_inputs (
    job_id uuid not null references jobs(id) on delete cascade,
    scene_id uuid references scenes(id),
    ref_asset_id uuid references reference_assets(id),
    role text not null,
    object_key_snapshot text
);

-- ---------------------------------------------------------------------------
-- Raster artifacts
-- ---------------------------------------------------------------------------

create table raster_artifacts (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    artifact_type text not null
        check (artifact_type in ('sr_output', 'uncertainty', 'preprocessed_tiles',
                                 'benchmark_output', 'reference_grid', 'report_file',
                                 'manifest', 'observation')),
    storage_bucket text not null,
    object_key text not null unique,
    checksum text,
    media_type text,
    crs text,
    width int,
    height int,
    resolution_m double precision,
    band_count int,
    bounds geometry(Polygon,4326),
    bytes bigint,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Validation / metrics / benchmarks / uncertainty / reports
-- ---------------------------------------------------------------------------

create table validation_runs (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    protocol_version text not null,
    evaluation_grid_m double precision not null default 2.5,
    reference_id uuid references reference_assets(id),
    queue_job_id uuid references jobs(id),
    request_fingerprint text,
    status text not null default 'RUNNING'
        check (status in ('RUNNING', 'COMPLETED', 'FAILED')),
    overall_status text check (overall_status in ('PASS', 'CAUTION', 'FAIL')),
    score double precision check (score >= 0 and score <= 1),
    notes text,
    created_at timestamptz not null default now()
);

create table validation_metrics (
    id uuid primary key default gen_random_uuid(),
    validation_run_id uuid not null references validation_runs(id) on delete cascade,
    metric_name text not null,
    band text,
    value double precision,
    normalized_value double precision,
    threshold double precision,
    pass boolean,
    details jsonb not null default '{}'::jsonb
);

create table benchmark_runs (
    id uuid primary key default gen_random_uuid(),
    validation_run_id uuid not null references validation_runs(id) on delete cascade,
    baseline_name text not null,
    model_version_id uuid references model_versions(id),
    result_artifact_id uuid references raster_artifacts(id),
    metrics jsonb,
    created_at timestamptz not null default now()
);

create table uncertainty_summaries (
    id uuid primary key default gen_random_uuid(),
    raster_artifact_id uuid not null references raster_artifacts(id) on delete cascade,
    mean double precision,
    p50 double precision,
    p90 double precision,
    p95 double precision,
    max double precision,
    coverage double precision,
    calibration jsonb
);

create table reports (
    id uuid primary key default gen_random_uuid(),
    validation_run_id uuid not null references validation_runs(id) on delete cascade,
    summary_json jsonb,
    report_object_key text,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Provenance
-- ---------------------------------------------------------------------------

create table provenance_events (
    id uuid primary key default gen_random_uuid(),
    project_id uuid references projects(id) on delete cascade,
    entity_type text not null,
    entity_id uuid,
    event_type text not null,
    actor text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
