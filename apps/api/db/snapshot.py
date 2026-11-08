"""Read access to the imported V2 snapshot.

The snapshot is the read source for every public and workspace query; Atlas
holds a published mirror. Every statement goes through here so that connection
handling and row conversion exist once, and so no SQL is written in a route.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from ..core import settings


class Missing(RuntimeError):
    """No snapshot has been imported yet."""


def path() -> Path:
    return settings.database_path()


def exists() -> bool:
    return path().is_file()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """A read connection that is always closed, with rows as mappings."""
    if not exists():
        raise Missing(str(path()))
    db = sqlite3.connect(path())
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def rows(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with connection() as db:
        return [dict(row) for row in db.execute(sql, params)]


def row(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    with connection() as db:
        found = db.execute(sql, params).fetchone()
    return dict(found) if found else None


def value(sql: str, params: Sequence[Any] = ()) -> Any:
    with connection() as db:
        found = db.execute(sql, params).fetchone()
    return found[0] if found else None
