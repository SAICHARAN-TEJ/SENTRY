-- 0012_hardening.sql
-- SIH26142 "Sentry" - constraint + seed-accuracy hardening.
--
-- 1. job_inputs.role: only the four roles the routers actually write
--    (backend/routers/jobs.py, backend/routers/validations.py). Anything else
--    is a caller bug and must fail at the database, not hide in history.
-- 2. dataset_sources license for WorldStrat: the seed said "see release".
--    The verified terms (data/worldstrat/LICENSE.txt, SOURCES.md) are CC
--    BY-NC 4.0 for the Airbus SPOT HR imagery, CC BY 4.0 for the Sentinel-2
--    layers/labels, BSD-3-Clause for the WorldStrat code. Stamp them so no
--    downstream report can claim unrestricted commercial use.
-- 3. opensr_ldsrs2 row version: the seed said "esa-opensr". The pinned
--    upstream release is v1.1.1 (SOURCES.md, worker/registry.py).

alter table public.job_inputs
    drop constraint if exists job_inputs_role_check;
alter table public.job_inputs
    add constraint job_inputs_role_check
    check (role in ('input', 'reference', 'aoi', 'source_job'));

update public.dataset_sources
    set license = 'CC BY-NC 4.0 (Airbus SPOT 6/7 HR imagery); '
                  'CC BY 4.0 (Sentinel-2 layers, labels, weights); '
                  'BSD-3-Clause (WorldStrat code). Non-commercial only for HR.'
    where name = 'worldstrat';

update public.model_versions
    set version = 'v1.1.1'
    where name = 'opensr_ldsrs2' and version <> 'v1.1.1';
