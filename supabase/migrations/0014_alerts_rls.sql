-- 0014_alerts_rls.sql
-- Depends on: 0013_alerts.sql, 0004_rls.sql
-- Secure the alerts domain created in 0013: qualify schema, enable RLS,
-- project-scoped policies reusing has_project_role(), plus missing index.

alter table public.alerts enable row level security;

create index if not exists alerts_validation_run_idx on public.alerts (validation_run_id);

drop policy if exists alerts_select_members on public.alerts;
create policy alerts_select_members on public.alerts
    for select to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator', 'reviewer', 'viewer']));

drop policy if exists alerts_insert_operators on public.alerts;
create policy alerts_insert_operators on public.alerts
    for insert to authenticated
    with check (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists alerts_update_operators on public.alerts;
create policy alerts_update_operators on public.alerts
    for update to authenticated
    using (public.has_project_role(project_id, array['owner', 'operator']))
    with check (public.has_project_role(project_id, array['owner', 'operator']));

drop policy if exists alerts_delete_owner on public.alerts;
create policy alerts_delete_owner on public.alerts
    for delete to authenticated
    using (public.has_project_role(project_id, array['owner']));
