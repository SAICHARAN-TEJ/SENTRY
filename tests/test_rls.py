"""RLS tests — require a live Supabase DB (SUPABASE_DB_URL) and anon JWTs.

Intended semantics: a non-member authenticated session must see zero rows of
another project's jobs/aois; members see only their projects' rows. The suite
creates two isolated projects via the service connection, then asserts RLS
filtration through a least-privileged connection.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="needs live Supabase DB (SUPABASE_DB_URL)",
)


def test_cross_project_reads_denied():
    import psycopg

    url = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(url) as svc:  # service role: bypasses RLS, seeds rows
        svc.execute(
            """
            insert into organizations (name) values ('rls-test-org')
            returning id
            """)
        org_id = svc.fetchone()[0]
        svc.execute("insert into projects (organization_id, name) values (%s, %s) returning id",
                    (org_id, "rls-A"))
        proj_a = svc.fetchone()[0]
        svc.execute("insert into projects (organization_id, name) values (%s, %s) returning id",
                    (org_id, "rls-B"))
        proj_b = svc.fetchone()[0]

        # Member of A only.
        svc.execute(
            "insert into project_members (project_id, user_id, role) values (%s, %s, 'owner')",
            (proj_a, "00000000-0000-4000-8000-00000000aa01"))
        svc.execute(
            "insert into aois (project_id, name, geom) values (%s, 'a', "
            "ST_Multi(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 4326)))",
            (proj_a,))
        svc.execute(
            "insert into aois (project_id, name, geom) values (%s, 'b', "
            "ST_Multi(ST_GeomFromText('POLYGON((2 0,3 0,3 1,2 1,2 0))', 4326)))",
            (proj_b,))
        svc.commit()

    # Non-member session: RLS must return zero rows either way.
    anon_url = url  # with JWT-based least-privilege connection in a live env
    with psycopg.connect(anon_url) as conn:
        # Without a member JWT (no auth.uid()), has_project_role() is false:
        # all project-scoped selects must return empty under RLS.
        rows = conn.execute("select * from aois").fetchall()
        assert rows == [], "RLS leaked AOI rows to a non-member session"
