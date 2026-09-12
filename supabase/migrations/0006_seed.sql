-- 0006_seed.sql
-- SIH26142 "Sentry" - deterministic dev/staging seed data.
-- Depends on: 0002_core_tables.sql, 0004_rls.sql.
-- All inserts are idempotent so `supabase db reset` is repeatable.

-- ---------------------------------------------------------------------------
-- Dataset sources
-- ---------------------------------------------------------------------------

insert into public.dataset_sources (id, name, version, source_type, provider, license, uri)
values
    ('00000000-0000-4000-8000-0000000000d1'::uuid,
     'sentinel-2-l2a', 's2-processing-baseline-04.00', 'satellite-l2a', 'copernicus',
     'Copernicus - free and open use', 'https://dataspace.copernicus.eu'),
    ('00000000-0000-4000-8000-0000000000d2'::uuid,
     'worldstrat', 'v1.1', 'reference-hr', 'worldstrat',
     'see release', 'https://zenodo.org/records/15382551'),
    ('00000000-0000-4000-8000-0000000000d3'::uuid,
     'sen2naip', 'v1', 'reference-hr', 'sen2naip',
     'see dataset paper', 'https://www.nature.com/articles/s41597-024-04214-y')
on conflict (name, version) do nothing;

-- ---------------------------------------------------------------------------
-- Model registry
-- ---------------------------------------------------------------------------

insert into public.model_versions (id, name, version, framework, model_card)
values
    ('00000000-0000-4000-8000-0000000000b1'::uuid,
     'bicubic_4x', '1.0.0', 'skimage',
     '{"role": "deterministic interpolation baseline"}'::jsonb),
    ('00000000-0000-4000-8000-0000000000b2'::uuid,
     'opensr_ldsrs2', 'esa-opensr', 'pytorch',
     '{"role": "primary published baseline", "repo": "https://github.com/ESAOpenSR/opensr-model"}'::jsonb),
    ('00000000-0000-4000-8000-0000000000b3'::uuid,
     'custom_mf_sr', '0.1.0', 'numpy',
     '{"role": "team multi-frame model"}'::jsonb),
    ('00000000-0000-4000-8000-0000000000b4'::uuid,
     'realesrgan_optional', 'visual-only', 'pytorch',
     '{"role": "visual-only auxiliary", "note": "never used as scientific comparator"}'::jsonb)
on conflict (name, version) do nothing;

-- ---------------------------------------------------------------------------
-- Demo organization / project / owner membership
-- ---------------------------------------------------------------------------

insert into public.organizations (id, name, created_by)
values ('00000000-0000-4000-8000-0000000000c1'::uuid, 'SIH26142 Demo',
        '00000000-0000-4000-8000-00000000aa01'::uuid)
on conflict (id) do nothing;

insert into public.projects (id, organization_id, name)
values ('00000000-0000-4000-8000-0000000000c2'::uuid,
        '00000000-0000-4000-8000-0000000000c1'::uuid, 'Demo Project')
on conflict (id) do nothing;

-- Placeholder dev user; only effective once that user exists in auth.users.
insert into public.project_members (project_id, user_id, role)
values ('00000000-0000-4000-8000-0000000000c2'::uuid,
        '00000000-0000-4000-8000-00000000aa01'::uuid, 'owner')
on conflict (project_id, user_id) do nothing;

-- ---------------------------------------------------------------------------
-- Validation protocol registration (existence-guarded for rerun idempotency)
-- ---------------------------------------------------------------------------

insert into public.provenance_events (project_id, entity_type, entity_id, event_type, actor, payload)
select
    '00000000-0000-4000-8000-0000000000c2'::uuid,
    'validation_protocol',
    null,
    'protocol_registered',
    'seed',
    '{"protocol_version": "sih26142_v1", "evaluation_grid_m": 2.5}'::jsonb
where not exists (
    select 1 from public.provenance_events pe
    where pe.project_id = '00000000-0000-4000-8000-0000000000c2'::uuid
      and pe.event_type = 'protocol_registered'
      and pe.payload ->> 'protocol_version' = 'sih26142_v1'
);
