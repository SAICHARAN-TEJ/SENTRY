-- 00_supabase_shim.sql
-- SIH26142 "Sentry" - LOCAL-ONLY compatibility shim.
--
-- supabase/migrations/*.sql are written against a real Supabase database, which
-- ships a pre-baked environment that a plain PostgreSQL server does not have:
--
--   * roles            anon, authenticated, service_role
--   * schema auth      auth.uid(), auth.jwt(), auth.users
--   * schema storage   storage.buckets, storage.objects (RLS-protected)
--   * publication      supabase_realtime
--
-- Those objects are created by the Supabase platform *before* any migration
-- runs, which is why the migrations never create them themselves. This file
-- recreates exactly that environment so the same migrations apply unchanged to
-- a plain  postgis/postgis  container (scripts/db_init.py).
--
-- It is deliberately NOT in supabase/migrations/:
--   * `supabase db reset` against a real Supabase project must never see it, and
--   * creating roles requires superuser, which a managed project will not grant.
--
-- Everything here is idempotent, so re-running a reset is safe.
--
-- SECURITY NOTE: this shim does not weaken RLS. It only supplies the roles and
-- helper functions the RLS policies already reference. auth.uid() reads the
-- request JWT the same way Supabase's does, so public.has_project_role() behaves
-- identically here and there.

-- ---------------------------------------------------------------------------
-- 1. Roles
--    Supabase grants API clients the `authenticated` role via the anon key and
--    reserves `service_role` for server-side connections that bypass RLS.
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        -- bypassrls mirrors the platform's service role, which is the whole
        -- reason workers may use it and browsers never may.
        create role service_role nologin noinherit bypassrls;
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2. auth schema
--    auth.uid() is the identity source for every RLS policy in 0004_rls.sql.
--    Supabase resolves it from the request JWT claims; we do the same, reading
--    either the modern `request.jwt.claims` JSON or the legacy singular claim.
-- ---------------------------------------------------------------------------
create schema if not exists auth;

create or replace function auth.uid()
returns uuid
language sql
stable
as $$
    select nullif(
        coalesce(
            current_setting('request.jwt.claim.sub', true),
            (nullif(current_setting('request.jwt.claims', true), '')::jsonb) ->> 'sub'
        ),
        ''
    )::uuid;
$$;

create or replace function auth.jwt()
returns jsonb
language sql
stable
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claims', true), '')::jsonb,
        '{}'::jsonb
    );
$$;

create or replace function auth.role()
returns text
language sql
stable
as $$
    select coalesce(auth.jwt() ->> 'role', current_user);
$$;

-- Minimal identity table. The application schema stores user ids as bare
-- uuids (project_members.user_id has no FK), so this exists only so a locally
-- seeded owner can be a real row rather than a dangling reference.
create table if not exists auth.users (
    id uuid primary key default gen_random_uuid(),
    email text unique,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 3. storage schema
--    0005_storage.sql inserts bucket rows and creates a policy on
--    storage.objects, so both tables must exist and carry RLS.
-- ---------------------------------------------------------------------------
create schema if not exists storage;

create table if not exists storage.buckets (
    id text primary key,
    name text not null,
    owner uuid,
    public boolean not null default false,
    file_size_limit bigint,
    allowed_mime_types text[],
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists storage.objects (
    id uuid primary key default gen_random_uuid(),
    bucket_id text references storage.buckets(id) on delete cascade,
    name text,
    owner uuid,
    metadata jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_accessed_at timestamptz not null default now()
);

create index if not exists idx_storage_objects_bucket_name
    on storage.objects (bucket_id, name);

alter table storage.buckets enable row level security;
alter table storage.objects enable row level security;

-- 0005_storage.sql extracts {project_id} from the first path segment; expose the
-- same helper Supabase ships so object paths resolve identically.
create or replace function storage.foldername(name text)
returns text[]
language plpgsql
immutable
as $$
declare
    parts text[];
begin
    if name is null then
        return array[]::text[];
    end if;
    parts := string_to_array(name, '/');
    return parts[1:array_length(parts, 1) - 1];
end;
$$;

-- ---------------------------------------------------------------------------
-- 4. Realtime publication
--    0004_rls.sql adds jobs/job_steps/validation_runs/raster_artifacts to it.
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
        create publication supabase_realtime;
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 5. Privileges
--    On Supabase, API roles are granted access to `public` at database
--    creation. RLS still decides row visibility; these grants only let a role
--    reach the table long enough for a policy to be evaluated.
-- ---------------------------------------------------------------------------
grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema storage to anon, authenticated, service_role;

alter default privileges in schema public
    grant select, insert, update, delete on tables to authenticated, service_role;
alter default privileges in schema public
    grant usage, select on sequences to authenticated, service_role;
alter default privileges in schema storage
    grant select, insert, update, delete on tables to authenticated, service_role;

-- auth.uid() must be callable from inside policies evaluated as a member role.
grant execute on function auth.uid() to anon, authenticated, service_role;
grant execute on function auth.jwt() to anon, authenticated, service_role;
grant execute on function auth.role() to anon, authenticated, service_role;
