"""Request-scoped PostgreSQL unit of work helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection, IsolationLevel
from psycopg_pool import ConnectionPool


class UnitOfWork:
    """Thin wrapper around a psycopg connection pool."""

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.pool.connection() as conn:
            yield conn

    @contextmanager
    def transaction(
        self,
        *,
        isolation_level: IsolationLevel | None = None,
    ) -> Iterator[Connection]:
        with self.pool.connection() as conn:
            if isolation_level is not None:
                conn.isolation_level = isolation_level
            with conn.transaction():
                yield conn

    def probe(self) -> bool:
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False
