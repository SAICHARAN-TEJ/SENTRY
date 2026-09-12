-- 0004_rls.sql
-- SIH26142 "Sentry" - row-level security, helper functions, realtime publication.
-- Depends on: 0002_core_tables.sql, 0003a_compatibility.sql, 0003b_indexes.sql.
-- NOTE: 0003_compatibility.sql runs before 0003_indexes.sql alphabetically
--
-- Model: project-scoped access via project_members (owner > operator > reviewer > viewer).
-- Workers connect with the service role (bypasses RLS server-side); clients use Supabase
-- Auth JWTs and can only reach rows in projects they belong to.

-- ---------------------------------------------------------------------------
-- Helper functions (security definer to avoid RLS recursion)
-- ---------------------------------------------------------------------------

create or replace function public.has_project_role(pid uuid, roles text[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from project_members pm
        where pm.project_id = pid
          and pm.user_id = auth.uid()
          and pm.role = any(roles)
    );
$$;

create or replace function public.is_service_role()
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    claims jsonb := '{}'::jsonb;
begin
    begin
        claims := coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
    exception when others then
        claims := '{}'::jsonb;
    end;
    -- session_user is used rather than current_user: SECURITY DEFINER changes
    -- current_user to the function owner (normally postgres).
    return coalesce(claims ->> 'role', '') = 'service_role'
        or session_user in ('postgres', 'supabase_admin', 'service_role');
end;
$$;

create or replace function public.has_job_project_role(jid uuid, roles text[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from jobs j
        where j.id = jid
          and public.has_project_role(j.project_id, roles)
    );
$$;

create or replace function public.has_vr_project_role(vrid uuid, roles text[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from validation_runs vr
        where vr.id = vrid
          and public.has_job_project_role(vr.job_id, roles)
    );
$$;

-- Membership helpers used by policies ON project_members/organizations themselves.
-- These must be SECURITY DEFINER (run as postgres, bypassing RLS) because a policy
-- subquery against the same table would trigger "infinite recursion in policy".

create or replace function public.is_project_owner(pid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from project_members pm
        where pm.project_id = pid
          and pm.user_id = auth.uid()
          and pm.role = 'owner'
    );
$$;

create or replace function public.is_org_member(oid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (select 1 from organizations o
                   where o.id = oid and o.created_by = auth.uid())
        or exists (
            select 1
            from project_members pm
            join projects p on p.id = pm.project_id
            where p.organization_id = oid
              and pm.user_id = auth.uid()
        );
$$;

create or replace function public.is_org_owner(oid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (select 1 from organizations o
                   where o.id = oid and o.created_by = auth.uid())
        or exists (
            select 1
            from project_members pm
            join projects p on p.id = pm.project_id
            where p.organization_id = oid
              and pm.user_id = auth.uid()
              and pm.role = 'owner'
        );
$$;

create or replace function public.can_create_project_in_org(oid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select public.is_org_owner(oid);
$$;

revoke all on function public.is_project_owner(uuid) from public;
revoke all on function public.is_org_member(uuid) from public;
revoke all on function public.is_org_owner(uuid) from public;
revoke all on function public.can_create_project_in_org(uuid) from public;
grant execute on function public.is_project_owner(uuid) to authenticated, service_role;
grant execute on function public.is_org_member(uuid) to authenticated, service_role;
grant execute on function public.is_org_owner(uuid) to authenticated, service_role;
grant execute on function public.can_create_project_in_org(uuid) to authenticated, service_role;
grant execute on function public.has_project_role(uuid, text[]) to authenticated, service_role;
grant execute on function public.is_service_role() to authenticated, service_role;
grant execute on function public.has_job_project_role(uuid, text[]) to authenticated, service_role;
grant execute on function public.has_vr_project_role(uuid, text[]) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Auto-add project creator as owner
-- ---------------------------------------------------------------------------

create or replace function public.add_project_owner()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is not null then
        insert into project_members (project_id, user_id, role)
        values (new.id, auth.uid(), 'owner')
        on conflict do nothing;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_add_project_owner on public.projects;
create trigger trg_add_project_owner
    after insert on public.projects
    for each row execute function public.add_project_owner();

-- ---------------------------------------------------------------------------
-- Enable RLS on all tables
-- ---------------------------------------------------------------------------

alter table public.organizations        enable row level security;
alter table public.projects            enable row level security;
alter table public.project_members     enable row level security;
alter table public.aois                enable row level security;
alter table public.dataset_sources     enable row level security;
alter table public.scenes              enable row level security;
alter table public.scene_bands         enable row level security;
alter table public.reference_assets    enable row level security;
alter table public.processing_configs  enable row level security;
alter table public.model_versions      enable row level security;
alter table public.jobs                enable row level security;
alter table public.job_steps           enable row level security;
alter table public.job_inputs          enable row level security;
alter table public.raster_artifacts    enable row level security;
alter table public.validation_runs     enable row level security;
alter table public.validation_metrics  enable row level security;
alter table public.benchmark_runs      enable row level security;
alter table public.uncertainty_summaries enable row level security;
alter table public.reports             enable row level security;
alter table public.provenance_events   enable row level security;

-- ---------------------------------------------------------------------------
-- organizations
-- ---------------------------------------------------------------------------

drop policy if exists org_select_members on public.organizations;
create policy org_select_members on public.organizations
    for select to authenticated
    using (public.is_org_member(id));

drop policy if exists org_insert_any on public.organizations;
create policy org_insert_any on public.organizations
    for insert to authenticated
    with check (auth.uid() is not null and created_by = auth.uid());

drop policy if exists org_update_owner on public.organizations;
create policy org_update_owner on public.organizations
    for update to authenticated
    using (public.is_org_owner(id));

drop policy if exists org_delete_owner on public.organizations;
create policy org_delete_owner on public.organizations
    for delete to authenticated
    using (public.is_org_owner(id));

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

drop policy if exists project_select_members on public.projects;
create policy project_select_members on public.projects
    for select to authenticated
    using (public.has_project_role(id, array['owner', 'operator', 'reviewer', 'viewer']));

-- Creating projects always requires ownership of the organization; ownership
-- is established explicitly by organizations.created_by even before the first
-- project exists.
drop policy if exists project_insert_any on public.projects;
create policy project_insert_any on public.projects
    for insert to authenticated
    with check (
        auth.uid() is not null
        and public.can_create_project_in_org(organization_id)
    );

drop policy if exists project_update_owner on public.projects;
create policy project_update_owner on public.projects
    for update to authenticated
    using (public.has_project_role(id, array['owner']));

drop policy if exists project_delete_owner on public.projects;
create policy project_delete_owner on public.projects
    for delete to authenticated
    using (public.has_project_role(id, array['owner']));

-- ---------------------------------------------------------------------------
-- project_members
-- NOTE: every policy here uses SECURITY DEFINER helpers (is_project_owner).
-- A policy subquery against project_members itself would recurse infinitely,
-- and self-service inserts would let any user escalate to 'owner'.
-- ---------------------------------------------------------------------------

drop policy if exists pm_select_self_or_owner on public.project_members;
create policy pm_select_self_or_owner on public.project_members
    for select to authenticated
    using (user_id = auth.uid() or public.is_project_owner(project_id));

-- Only existing owners may add members; nobody can self-enroll.
-- (Creator ownership is granted by the add_project_owner() trigger.)
drop policy if exists pm_insert_owner on public.project_members;
create policy pm_insert_owner on public.project_members
    for insert to authenticated
    with check (
        public.is_project_owner(project_id)
        and role in ('owner', 'operator', 'reviewer', 'viewer')
    );

drop policy if exists pm_update_owner on public.project_members;
create policy pm_update_owner on public.project_members
    for update to authenticated
    using (public.is_project_owner(project_id));

drop policy if exists pm_delete_owner on public.project_members;
create policy pm_delete_owner on public.project_members
    for delete to authenticated
    using (public.is_project_owner(project_id));

-- ---------------------------------------------------------------------------
-- aois - read all roles, write owner+operator
-- ---------------------------------------------------------------------------

drop policy if exists aoi_select_members on public.aois;
create policy aoi_select_members on public.aois
    for select to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists aoi_insert_ops on public.aois;
create policy aoi_insert_ops on public.aois
    for insert to authenticated
    with check (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists aoi_update_ops on public.aois;
create policy aoi_update_ops on public.aois
    for update to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists aoi_delete_ops on public.aois;
create policy aoi_delete_ops on public.aois
    for delete to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator']));

-- ---------------------------------------------------------------------------
-- Catalog tables - readable by authenticated, writable only via service role
-- (no authenticated write policies: service role bypasses RLS)
-- ---------------------------------------------------------------------------

drop policy if exists dataset_source_select on public.dataset_sources;
create policy dataset_source_select on public.dataset_sources
    for select to authenticated using (true);

drop policy if exists scene_select on public.scenes;
create policy scene_select on public.scenes
    for select to authenticated using (true);

drop policy if exists scene_band_select on public.scene_bands;
create policy scene_band_select on public.scene_bands
    for select to authenticated using (true);

drop policy if exists reference_asset_select on public.reference_assets;
create policy reference_asset_select on public.reference_assets
    for select to authenticated using (true);

drop policy if exists model_version_select on public.model_versions;
create policy model_version_select on public.model_versions
    for select to authenticated using (true);

-- ---------------------------------------------------------------------------
-- processing_configs - read all roles, write owner+operator
-- ---------------------------------------------------------------------------

drop policy if exists config_select_members on public.processing_configs;
create policy config_select_members on public.processing_configs
    for select to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists config_insert_ops on public.processing_configs;
create policy config_insert_ops on public.processing_configs
    for insert to authenticated
    with check (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists config_update_ops on public.processing_configs;
create policy config_update_ops on public.processing_configs
    for update to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists config_delete_ops on public.processing_configs;
create policy config_delete_ops on public.processing_configs
    for delete to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator']));

-- ---------------------------------------------------------------------------
-- jobs - read via project membership, insert by owner+operator, workers write
-- with service role (bypasses RLS)
-- ---------------------------------------------------------------------------

drop policy if exists job_select_members on public.jobs;
create policy job_select_members on public.jobs
    for select to authenticated
    using (public.has_job_project_role(id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists job_insert_ops on public.jobs;
create policy job_insert_ops on public.jobs
    for insert to authenticated
    with check (public.has_project_role(project_id, array['owner', 'operator']));

-- ---------------------------------------------------------------------------
-- job_steps / job_inputs - read via parent job
-- ---------------------------------------------------------------------------

drop policy if exists job_step_select_members on public.job_steps;
create policy job_step_select_members on public.job_steps
    for select to authenticated
    using (public.has_job_project_role(job_id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists job_input_select_members on public.job_inputs;
create policy job_input_select_members on public.job_inputs
    for select to authenticated
    using (public.has_job_project_role(job_id, array['owner', 'operator', 'reviewer', 'viewer']));

-- ---------------------------------------------------------------------------
-- raster_artifacts - read via parent job
-- ---------------------------------------------------------------------------

drop policy if exists artifact_select_members on public.raster_artifacts;
create policy artifact_select_members on public.raster_artifacts
    for select to authenticated
    using (public.has_job_project_role(job_id, array['owner', 'operator', 'reviewer', 'viewer']));

-- ---------------------------------------------------------------------------
-- validation_runs - read via parent job
-- ---------------------------------------------------------------------------

drop policy if exists vr_select_members on public.validation_runs;
create policy vr_select_members on public.validation_runs
    for select to authenticated
    using (public.has_job_project_role(job_id, array['owner', 'operator', 'reviewer', 'viewer']));

-- ---------------------------------------------------------------------------
-- validation_metrics / benchmark_runs - read via validation_run -> job
-- ---------------------------------------------------------------------------

drop policy if exists vm_select_members on public.validation_metrics;
create policy vm_select_members on public.validation_metrics
    for select to authenticated
    using (public.has_vr_project_role(validation_run_id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists benchmark_select_members on public.benchmark_runs;
create policy benchmark_select_members on public.benchmark_runs
    for select to authenticated
    using (public.has_vr_project_role(validation_run_id, array['owner', 'operator', 'reviewer', 'viewer']));

-- ---------------------------------------------------------------------------
-- uncertainty_summaries - read via raster_artifact -> job
-- ---------------------------------------------------------------------------

drop policy if exists unc_select_members on public.uncertainty_summaries;
create policy unc_select_members on public.uncertainty_summaries
    for select to authenticated
    using (
        exists (
            select 1
            from public.raster_artifacts ra
            where ra.id = uncertainty_summaries.raster_artifact_id
              and public.has_job_project_role(ra.job_id, array['owner', 'operator', 'reviewer', 'viewer'])
        )
    );

-- ---------------------------------------------------------------------------
-- reports - read via validation_run -> job
-- ---------------------------------------------------------------------------

drop policy if exists report_select_members on public.reports;
create policy report_select_members on public.reports
    for select to authenticated
    using (public.has_vr_project_role(validation_run_id, array['owner', 'operator', 'reviewer', 'viewer']));

-- ---------------------------------------------------------------------------
-- provenance_events - read via project membership
-- ---------------------------------------------------------------------------

drop policy if exists provenance_select_members on public.provenance_events;
create policy provenance_select_members on public.provenance_events
    for select to authenticated
    using (
        project_id is not null
        and public.has_project_role(project_id, array['owner', 'operator', 'reviewer', 'viewer'])
    );

-- ---------------------------------------------------------------------------
-- Realtime publication (idempotent)
-- ---------------------------------------------------------------------------

do $$
begin
    execute 'alter publication supabase_realtime add table public.jobs';
exception
    when duplicate_object then null;
    when undefined_object then null;
end $$;

do $$
begin
    execute 'alter publication supabase_realtime add table public.job_steps';
exception
    when duplicate_object then null;
    when undefined_object then null;
end $$;

do $$
begin
    execute 'alter publication supabase_realtime add table public.validation_runs';
exception
    when duplicate_object then null;
    when undefined_object then null;
end $$;

do $$
begin
    execute 'alter publication supabase_realtime add table public.raster_artifacts';
exception
    when duplicate_object then null;
    when undefined_object then null;
end $$;
