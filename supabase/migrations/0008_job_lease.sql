-- 0008_job_lease.sql
-- SIH26142 "Sentry" - job lease/fencing: stale CLAIMED jobs can never pile up.
--
-- Problem: claim_job() moved jobs to CLAIMED with FOR UPDATE SKIP LOCKED, but
-- nothing watched the claim. A worker that crashed mid-job left the row
-- CLAIMED forever - never retried, never failed, invisible to the idempotency
-- "active job" check, so a resubmit with the same key returned the zombie.
--
-- Fix, three parts:
--   1. Lease:   claiming stamps lease_expires_at (= now + lease timeout) and a
--               fresh claim_token; a worker heartbeat renews the lease while
--               it runs, so the lease only lapses when the worker is gone.
--   2. Reaper:  reap_stale_jobs() requeues claims whose lease expired, up to
--               jobs.attempt < JOB_MAX_ATTEMPTS; beyond that it fails the job
--               permanently with error_code LEASE_LOST.
--   3. Fencing: transitions carry the claim_token; a requeued attempt gets a
--               new token, so a zombie worker's late writes cannot move the
--               requeued job (its transitions raise JOB_CONFLICT instead).

alter table public.jobs
    add column if not exists claim_token uuid,
    add column if not exists lease_expires_at timestamptz,
    add column if not exists attempt int not null default 0;

-- Requeue scan: non-terminal CLAIMED jobs with an expired lease, oldest first.
create index if not exists jobs_stale_claim_idx
    on public.jobs (lease_expires_at)
    where status = 'CLAIMED';

-- Claim scan: pick QUEUED work efficiently.
create index if not exists jobs_claim_idx
    on public.jobs (priority asc, created_at asc)
    where status = 'QUEUED';

-- job_steps: cap retries per step so a poison job cannot loop forever.
alter table public.job_steps
    add column if not exists attempt_cap int not null default 5;
