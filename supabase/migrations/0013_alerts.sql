-- 0013_alerts.sql
-- Minimal real alerts domain: detections derived from completed jobs.
-- Every alert links to the job + validation that produced it, so the
-- console can show real rows when the backend has them and fall back to
-- clearly-labeled demo content only when no rows exist.

create table alerts (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    job_id uuid references jobs(id) on delete cascade,
    validation_run_id uuid references validation_runs(id) on delete set null,
    title text not null default 'sub-pixel change candidate',
    classification text not null default 'HUMAN_REVIEW',
    confidence double precision check (confidence is null or (confidence >= 0 and confidence <= 1)),
    status text not null default 'HUMAN_REVIEW'
        check (status in ('HUMAN_REVIEW', 'CONFIRMED', 'DISMISSED')),
    material_delta text,
    coord_lat double precision,
    coord_lon double precision,
    notes text,
    created_at timestamptz not null default now()
);

create index alerts_project_idx on alerts (project_id, created_at desc);
create index alerts_job_idx on alerts (job_id);
