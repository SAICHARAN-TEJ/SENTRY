-- 99_local_grants.sql
-- SIH26142 "Sentry" - LOCAL-ONLY privilege pass, applied after the migrations.
--
-- Why this exists: on a real Supabase project, API roles are granted access to
-- every public object at database creation, so `authenticated` can reach a table
-- and let RLS decide row visibility. A freshly created local schema has no such
-- grants, which means a policy can never even be evaluated and RLS tests would
-- fail for the wrong reason ("permission denied for table") instead of exercising
-- the policy.
--
-- This file grants *access*, not *visibility*: `authenticated` does NOT get
-- BYPASSRLS, so every 0004_rls.sql policy still applies to it unchanged.
-- `service_role` is bypassrls by construction, mirroring Supabase.
--
-- Safe to re-run.

grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema storage to anon, authenticated, service_role;

grant select, insert, update, delete on all tables in schema public
    to authenticated, service_role;
grant usage, select on all sequences in schema public
    to authenticated, service_role;
grant execute on all functions in schema public
    to authenticated, service_role;

grant select, insert, update, delete on all tables in schema storage
    to authenticated, service_role;

-- `anon` is the pre-login role: it may read nothing project-scoped. It is granted
-- only enough to let a request arrive, and every policy is scoped `to
-- authenticated`, so an unauthenticated caller sees zero rows.
revoke all on all tables in schema public from anon;

-- Keep future objects consistent with the two statements above.
alter default privileges in schema public
    grant select, insert, update, delete on tables to authenticated, service_role;
alter default privileges in schema public
    grant usage, select on sequences to authenticated, service_role;
alter default privileges in schema public
    grant execute on functions to authenticated, service_role;
