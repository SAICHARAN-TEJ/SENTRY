"""Provision a local Postgres/PostGIS database for SENTRY (dev + CI helper).

The application has no offline database mode: ``backend/db.py`` talks to a real
Postgres through ``SUPABASE_DB_URL`` and the schema itself is defined by the
versioned migrations under ``supabase/migrations/``. This script stands that
database up locally, in the same order a real Supabase project would:

  1. ``supabase/local/00_supabase_shim.sql``  roles, ``auth``/``storage`` schemas,
                                              ``auth.uid()``, realtime publication
  2. ``supabase/migrations/*.sql``            the real, versioned schema (0001..)
  3. ``supabase/local/99_local_grants.sql``   local privileges so RLS is evaluable

Usage
-----
    python scripts/db_init.py --recreate   # drop schemas, rebuild from scratch
    python scripts/db_init.py              # apply to a database with no schema yet
    python scripts/db_init.py --verify     # round-trip check only, no DDL

Connection string resolution order:
    --url  ->  $SUPABASE_DB_URL  ->  .env  ->  the local container default.

``--recreate`` is destructive by design and never the default: it drops the
``public``, ``auth`` and ``storage`` schemas. It is the equivalent of
``supabase db reset`` and is what a repeatable local run should use.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

MIGRATIONS_DIR = REPO / "supabase" / "migrations"
LOCAL_DIR = REPO / "supabase" / "local"
ENV_FILE = REPO / ".env"

# Matches the container started by the documented local setup. Only ever used
# when nothing else is configured, and it is deliberately a loopback address.
LOCAL_DEFAULT_URL = "postgresql://postgres:sentry_local_dev@127.0.0.1:54322/postgres"

SHIM = LOCAL_DIR / "00_supabase_shim.sql"
GRANTS = LOCAL_DIR / "99_local_grants.sql"

DROP_SCHEMAS = """
drop schema if exists public cascade;
drop schema if exists auth cascade;
drop schema if exists storage cascade;
drop extension if exists postgis cascade;
create schema public;
"""


def env_file_value(key: str) -> str:
    """Read one key from .env without importing the settings layer."""
    if not ENV_FILE.exists():
        return ""
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def resolve_url(cli_url: str) -> str:
    import os

    return (
        cli_url
        or os.environ.get("SUPABASE_DB_URL", "").strip()
        or env_file_value("SUPABASE_DB_URL")
        or LOCAL_DEFAULT_URL
    )


def redact(url: str) -> str:
    """Never print a password into logs."""
    if "@" not in url or "//" not in url:
        return url
    scheme, _, rest = url.partition("//")
    userinfo, _, host = rest.partition("@")
    user = userinfo.split(":", 1)[0]
    return f"{scheme}//{user}:***@{host}"


def apply_sql_file(conn: psycopg.Connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with conn.transaction():
        conn.execute(sql)


def migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"no migrations found under {MIGRATIONS_DIR}")
    return files


def provision(conn: psycopg.Connection, recreate: bool) -> None:
    if recreate:
        print("[0/3] recreating schemas public/auth/storage (destructive)")
        with conn.transaction():
            conn.execute(DROP_SCHEMAS)

    print(f"[1/3] applying local shim      {SHIM.name}")
    apply_sql_file(conn, SHIM)

    print("[2/3] applying migrations")
    for path in migration_files():
        apply_sql_file(conn, path)
        print(f"      ok  {path.name}")

    print(f"[3/3] applying local grants    {GRANTS.name}")
    apply_sql_file(conn, GRANTS)


def verify(conn: psycopg.Connection) -> bool:
    """Prove data can go in and come back out, including a spatial round-trip."""
    checks: list[tuple[str, bool, str]] = []

    tables = conn.execute(
        """
        select count(*) from information_schema.tables
        where table_schema = 'public' and table_type = 'BASE TABLE'
        """
    ).fetchone()[0]
    checks.append(("core tables present", tables >= 20, f"{tables} tables"))

    rls = conn.execute(
        """
        select count(*) from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relrowsecurity
        """
    ).fetchone()[0]
    checks.append(("row level security enabled", rls >= 18, f"{rls} tables"))

    policies = conn.execute(
        "select count(*) from pg_policies where schemaname = 'public'"
    ).fetchone()[0]
    checks.append(("RLS policies installed", policies >= 20, f"{policies} policies"))

    models = conn.execute(
        "select name, status, coalesce(left(checksum, 12), '-') "
        "from public.model_versions order by name"
    ).fetchall()
    published = [m for m in models if m[1] == "published"]
    checks.append(
        ("model registry populated", len(models) >= 4,
         f"{len(models)} rows, {len(published)} published")
    )

    # Real write/read round-trip on the tables the pipeline actually uses.
    # Rolled back so verification leaves no residue behind.
    try:
        with conn.transaction(force_rollback=True):
            org = conn.execute(
                "insert into public.organizations (name) values ('db_init verify') "
                "returning id"
            ).fetchone()[0]
            project = conn.execute(
                "insert into public.projects (organization_id, name) values (%s, 'verify') "
                "returning id",
                (org,),
            ).fetchone()[0]
            conn.execute(
                """
                insert into public.aois (project_id, name, geom)
                values (%s, 'verify-aoi',
                        ST_Multi(ST_GeomFromText('POLYGON((77 12, 77.05 12, 77.05 12.05, 77 12.05, 77 12))', 4326)))
                """,
                (project,),
            )
            job = conn.execute(
                """
                insert into public.jobs (project_id, job_type, idempotency_key)
                values (%s, 'reconstruct', 'verify-key') returning id, status
                """,
                (project,),
            ).fetchone()

            row = conn.execute(
                """
                select j.status,
                       a.name,
                       ST_AsText(a.geom),
                       round(ST_Area(a.geom::geography)::numeric, 1)
                from public.jobs j
                join public.aois a on a.project_id = j.project_id
                where j.id = %s
                """,
                (job[0],),
            ).fetchone()

            wrote = (
                row is not None
                and row[0] == "QUEUED"
                and "MULTIPOLYGON" in row[2]
                and float(row[3]) > 0
            )
            detail = (
                f"job {row[0]}, aoi {row[1]}, area {row[3]} m2" if row else "no row read back"
            )
            checks.append(("catalogue + geometry round-trip", wrote, detail))
    except psycopg.Error as exc:
        checks.append(("catalogue + geometry round-trip", False, str(exc).splitlines()[0]))

    print("\nverification")
    ok = True
    for name, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name:<34} {detail}")
        ok = ok and passed

    if models:
        print("\nmodel registry")
        for name, status, checksum in models:
            print(f"  {name:<22} {status:<12} sha256:{checksum}...")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="", help="Postgres connection string")
    parser.add_argument("--recreate", action="store_true",
                        help="drop public/auth/storage and rebuild (destructive)")
    parser.add_argument("--verify", action="store_true",
                        help="run verification only; apply no DDL")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip verification after provisioning")
    args = parser.parse_args()

    url = resolve_url(args.url)
    print(f"target: {redact(url)}")

    try:
        conn = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as exc:
        print(f"\nFAILED to connect: {exc}", file=sys.stderr)
        print("\nIs the local database running? See README.md > Local database.",
              file=sys.stderr)
        return 2

    with conn:
        if not args.verify:
            provision(conn, recreate=args.recreate)
        if not args.no_verify:
            return 0 if verify(conn) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
