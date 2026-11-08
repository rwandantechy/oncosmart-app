"""Shared MongoDB Atlas access.

One client per process, built lazily from ``MONGODB_URI`` so the snapshot
endpoints keep working when Atlas is not configured. Both the authentication
store and the Atlas export go through here rather than opening their own
connections.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from ..core import settings


class NotConfigured(RuntimeError):
    """``MONGODB_URI`` is unset, so there is nothing to connect to."""


def uri() -> str | None:
    """The configured connection string, or None when Atlas is not set up."""
    return os.getenv("MONGODB_URI") or None


@lru_cache(maxsize=4)
def _client(connection: str, timeout_ms: int) -> MongoClient:
    return MongoClient(connection, serverSelectionTimeoutMS=timeout_ms)


def client() -> MongoClient:
    connection = uri()
    if not connection:
        raise NotConfigured("MONGODB_URI is not set")
    return _client(connection, settings.MONGO_TIMEOUT_MS)


def database() -> Database:
    return client()[settings.auth_database()]


def collection(name: str) -> Collection:
    return database()[name]
