-- 0005_storage.sql
-- SIH26142 "Sentry" - storage buckets and object access policies.
-- Depends on: 0004_rls.sql (has_project_role helper).
--
-- Buckets:
--   private, service-only:      raw-ingest, scene-assets, model-artifacts
--   project-scoped member read: references, sr-outputs, uncertainty, benchmarks, reports
-- Workers use the service role (bypasses storage RLS) server-side only.

insert into storage.buckets (id, name, public)
values
    ('raw-ingest',     'raw-ingest',     false),
    ('scene-assets',   'scene-assets',   false),
    ('references',     'references',     false),
    ('sr-outputs',     'sr-outputs',     false),
    ('uncertainty',    'uncertainty',    false),
    ('benchmarks',     'benchmarks',     false),
    ('reports',        'reports',        false),
    ('model-artifacts','model-artifacts',false)
on conflict (id) do nothing;

-- Extract project uuid from object name's first path segment: {project_id}/...
create or replace function public.storage_object_project(obj_name text)
returns uuid
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    seg text;
    pid uuid;
begin
    if obj_name is null then
        return null;
    end if;
    seg := split_part(obj_name, '/', 1);
    begin
        pid := seg::uuid;
    exception
        when invalid_text_representation then
            return null;
    end;
    return pid;
end;
$$;

-- Project members can read project-scoped artifacts.
drop policy if exists "project artifacts read" on storage.objects;
create policy "project artifacts read" on storage.objects
    for select to authenticated
    using (
        bucket_id in ('sr-outputs', 'uncertainty', 'benchmarks', 'reports', 'references')
        and public.storage_object_project(name) is not null
        and public.has_project_role(
            public.storage_object_project(name),
            array['owner', 'operator', 'reviewer', 'viewer']
        )
    );

-- Intentionally NO authenticated write policies on any bucket:
-- uploads/writes go through the backend with the service-role key only.
