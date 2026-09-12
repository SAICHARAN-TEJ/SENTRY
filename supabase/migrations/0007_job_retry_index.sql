-- 0007_job_retry_index.sql
-- SIH26142 "Sentry" - idempotency without destroying audit history (FR-12/FR-14).
--
-- The original unique(project_id, idempotency_key) forced the API to DELETE a
-- terminal-failed job before creating a retry, cascading away its steps,
-- inputs, artifacts and validation runs. Replace it with a PARTIAL unique
-- index that enforces "at most one ACTIVE job per idempotency key" while
-- keeping FAILED/CANCELLED attempts archived forever.

drop index if exists jobs_project_id_idempotency_key_idx;

alter table public.jobs
    drop constraint if exists jobs_project_id_idempotency_key_key;

-- Drop whichever name PostgreSQL assigned to the original two-column unique
-- constraint; do not rely on an auto-generated suffix.
do $$
declare
    constraint_name text;
begin
    select c.conname into constraint_name
    from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    join pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'public'
      and t.relname = 'jobs'
      and c.contype = 'u'
      and (
          select array_agg(a.attname order by u.ord)
          from unnest(c.conkey) with ordinality u(attnum, ord)
          join pg_attribute a on a.attrelid = t.oid and a.attnum = u.attnum
      ) = array['project_id', 'idempotency_key']::name[];
    if constraint_name is not null then
        execute format('alter table public.jobs drop constraint %I', constraint_name);
    end if;
end $$;

-- At most one non-terminal job per (project_id, idempotency_key).
do $$
begin
    if exists (
        select 1
        from public.jobs
        where status not in ('FAILED', 'CANCELLED')
        group by project_id, idempotency_key
        having count(*) > 1
    ) then
        raise exception using
            message = 'Cannot create active idempotency index: duplicate active jobs exist',
            hint = 'Reconcile duplicate active jobs deliberately before rerunning this migration.';
    end if;
end $$;

create unique index if not exists jobs_active_idempotency_idx
    on public.jobs (project_id, idempotency_key)
    where status not in ('FAILED', 'CANCELLED');

-- Duplicate-band guard: scene_bands must have exactly one row per band.
do $$
begin
    if exists (
        select 1 from public.scene_bands
        group by scene_id, band_name having count(*) > 1
    ) then
        raise exception using
            message = 'Cannot enforce scene_bands uniqueness: duplicate (scene_id, band_name) rows exist',
            hint = 'Resolve duplicate rows deliberately, preserving the authoritative object/checksum, then rerun the migration.';
    end if;
end $$;

create unique index if not exists scene_bands_scene_band_idx
    on public.scene_bands (scene_id, band_name);

do $$
begin
    if exists (
        select 1
        from public.uncertainty_summaries
        group by raster_artifact_id having count(*) > 1
    ) then
        raise exception using
            message = 'Cannot enforce uncertainty summary uniqueness: duplicate artifact summaries exist',
            hint = 'Reconcile duplicate summaries deliberately before rerunning this migration.';
    end if;
    if exists (
        select 1
        from public.reports
        group by validation_run_id having count(*) > 1
    ) then
        raise exception using
            message = 'Cannot enforce report uniqueness: duplicate validation reports exist',
            hint = 'Reconcile duplicate reports deliberately before rerunning this migration.';
    end if;
end $$;

create unique index if not exists uncertainty_summary_artifact_idx
    on public.uncertainty_summaries (raster_artifact_id);

create unique index if not exists reports_validation_run_idx
    on public.reports (validation_run_id);

-- The job/validation link is one-to-one for explicit validation requests.
-- Existing duplicates are rejected by the preflight in compatibility/index
-- upgrades rather than silently selecting an arbitrary run.

-- Observation-space COG is a first-class artifact used by Component D.
-- Drop any pre-existing artifact-type check, regardless of PostgreSQL's
-- auto-generated constraint name, before installing the expanded check.
do $$
declare
    check_name text;
begin
    for check_name in
        select c.conname
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'raster_artifacts'
          and c.contype = 'c'
          and pg_get_constraintdef(c.oid) like '%artifact_type%'
    loop
        execute format('alter table public.raster_artifacts drop constraint %I', check_name);
    end loop;
end $$;

alter table public.raster_artifacts
    add constraint raster_artifacts_artifact_type_check
    check (artifact_type in (
        'sr_output', 'uncertainty', 'preprocessed_tiles', 'benchmark_output',
        'reference_grid', 'report_file', 'manifest', 'observation'
    ));
