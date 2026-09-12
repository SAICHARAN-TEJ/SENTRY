"""Postgres access layer (lazy psycopg pool, module-level monkeypatchable helpers)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
import psycopg.rows
from psycopg_pool import ConnectionPool

from backend.config import get_settings
from backend.errors import ApiError, AUTH_FORBIDDEN

_pool: ConnectionPool | None = None


class Session:
    """Queries bound to one connection/transaction."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def query(self, sql: str, params: Any = None, *, one: bool = False) -> Any:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return None
            rows: list[dict] = cur.fetchall()
        return (rows[0] if rows else None) if one else rows

    def execute(self, sql: str, params: Any = None) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


class LocalSession:
    """Transaction-shaped proxy for explicitly configured offline tests."""

    def query(self, sql: str, params: Any = None, *, one: bool = False) -> Any:
        return query(sql, params, one=one)

    def execute(self, sql: str, params: Any = None) -> int:
        return execute(sql, params)


def get_pool() -> ConnectionPool:
    """Lazily create the connection pool from SUPABASE_DB_URL."""
    global _pool
    if _pool is None:
        url = get_settings().supabase_db_url
        if not url:
            raise ApiError(AUTH_FORBIDDEN, "database not configured", 500)
        _pool = ConnectionPool(url, min_size=1, max_size=4, open=True)
    return _pool


@contextmanager
def transaction() -> Iterator[Session | LocalSession]:
    """Yield a dict-row session; commit atomically or roll back on exception."""
    if not get_settings().supabase_db_url:
        # Used only by the test/dev in-memory DB. Production must configure a
        # real connection and receives genuine ACID transaction semantics.
        yield LocalSession()
        return
    with get_pool().connection() as conn:
        conn.row_factory = psycopg.rows.dict_row
        with conn.transaction():
            yield Session(conn)


def query(sql: str, params: Any = None, *, one: bool = False) -> Any:
    """Execute a statement returning rows as dicts.

    ``one=True`` returns a single dict or ``None``; otherwise a list of dicts.
    The return type is intentionally ``Any``-compatible so strict checkers treat
    each call site by its ``one=`` flag (runtime type is exactly as documented).
    """
    with get_pool().connection() as conn:
        conn.row_factory = psycopg.rows.dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:  # statement returned no rows
                return None
            rows: list[dict] = cur.fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, params: Any = None) -> int:
    """Execute a mutation and return the affected row count."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            count = cur.rowcount
        conn.commit()
    return count
