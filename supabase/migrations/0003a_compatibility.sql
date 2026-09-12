-- 0003a_compatibility.sql
-- Compatibility columns required by the ownership and queue layers. This
-- migration intentionally runs before 0004_rls.sql. It is harmless on a
-- fresh database (0002 already declares the columns) and upgrades older
-- deployments without guessing an owner for existing organizations.

alter table public.organizations
    add column if not exists created_by uuid;

alter table public.jobs
    add column if not exists mode text not null default 'reconstruct_validate';

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.jobs'::regclass
          and conname = 'jobs_mode_check'
    ) then
        alter table public.jobs add constraint jobs_mode_check
            check (mode in ('preprocess', 'reconstruct', 'reconstruct_validate',
                            'validate', 'benchmark'));
    end if;
end $$;

do $$
begin
    if exists (
        select 1 from public.jobs
        where mode not in ('preprocess', 'reconstruct', 'reconstruct_validate',
                           'validate', 'benchmark')
    ) then
        raise exception using
            message = 'jobs.mode contains unsupported values',
            hint = 'Map legacy modes explicitly before rerunning migrations.';
    end if;
end $$;

-- Older databases may already contain invalid/unknown mode values. Do not
-- silently rewrite them; fail with a useful migration error before policies
-- and workers begin relying on the invariant.
-- (Single guard block; duplicates removed.)
alter table public.validation_runs
    add column if not exists queue_job_id uuid references public.jobs(id);

alter table public.validation_runs
    add column if not exists request_fingerprint text;

create unique index if not exists validation_runs_queue_job_idx
    on public.validation_runs (queue_job_id)
    where queue_job_id is not null;

create unique index if not exists validation_runs_request_fingerprint_idx
    on public.validation_runs (job_id, request_fingerprint)
    where request_fingerprint is not null;
