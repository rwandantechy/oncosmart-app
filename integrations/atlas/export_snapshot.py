"""Publish the active V2 SQLite snapshot to MongoDB Atlas.

The SQLite snapshot remains the read source for the API; this publishes a
mirror for use outside it, so run it again after any re-import.

Mirrors the V1 import boundary: read the active snapshot, verify it against its
recorded row count, write every record, then remove anything left over from a
superseded snapshot. ``record_id`` is the document ``_id``, so re-running is an
idempotent upsert rather than a duplicate load.

Usage:
    PYTHONPATH=. uv run python integrations/atlas/export_snapshot.py --dry-run
    PYTHONPATH=. uv run python integrations/atlas/export_snapshot.py
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.errors import PyMongoError

from apps.api.core import settings
from apps.api.db import mongo

# Fields the API filters and sorts on, so the Atlas copy can serve the same
# queries without a collection scan.
ALERT_INDEXES = (
    ("publish_date", DESCENDING),
    ("source_org", ASCENDING),
    ("source_country", ASCENDING),
    ("product_name", ASCENDING),
    ("snapshot_id", ASCENDING),
)

BATCH_SIZE = 500


class ExportError(RuntimeError):
    """The snapshot is missing, inconsistent, or Atlas rejected the write."""


def _rows(
    connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params)]


def read_active_snapshot(database: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The active snapshot row and its alerts, verified against the row count."""
    if not database.is_file():
        raise ExportError(f"No V2 snapshot at {database}")
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        snapshots = _rows(connection, "SELECT * FROM snapshots WHERE status = 'active'")
        if not snapshots:
            raise ExportError("The V2 database holds no active snapshot")
        if len(snapshots) > 1:
            raise ExportError(f"{len(snapshots)} snapshots are marked active; expected one")
        snapshot = snapshots[0]
        alerts = _rows(
            connection,
            "SELECT * FROM alerts WHERE snapshot_id = ? ORDER BY publish_date DESC",
            (snapshot["version_id"],),
        )
    if len(alerts) != snapshot["row_count"]:
        raise ExportError(
            f"Snapshot {snapshot['version_id']} records {snapshot['row_count']} rows "
            f"but holds {len(alerts)}"
        )
    return snapshot, alerts


def export_snapshot(database: Path, dry_run: bool = False) -> dict[str, Any]:
    snapshot, alerts = read_active_snapshot(database)
    plan = {
        "snapshot": snapshot["version_id"],
        "records": len(alerts),
        "database": settings.auth_database(),
        "alerts_collection": settings.ALERTS_COLLECTION,
        "snapshots_collection": settings.SNAPSHOTS_COLLECTION,
        "dry_run": dry_run,
    }
    if dry_run:
        return plan

    if not mongo.uri():
        raise ExportError("MONGODB_URI is not set, so there is no Atlas to publish to")

    try:
        collection = mongo.collection(settings.ALERTS_COLLECTION)
        snapshots = mongo.collection(settings.SNAPSHOTS_COLLECTION)

        for field, direction in ALERT_INDEXES:
            collection.create_index([(field, direction)])

        written = 0
        for start in range(0, len(alerts), BATCH_SIZE):
            batch = alerts[start : start + BATCH_SIZE]
            result = collection.bulk_write(
                [
                    UpdateOne(
                        {"_id": row["record_id"]},
                        {"$set": {key: value for key, value in row.items() if key != "record_id"}},
                        upsert=True,
                    )
                    for row in batch
                ],
                ordered=False,
            )
            written += result.upserted_count + result.modified_count + result.matched_count

        # Anything not in the active snapshot belongs to a superseded load.
        removed = collection.delete_many({"snapshot_id": {"$ne": snapshot["version_id"]}})
        snapshots.update_one(
            {"_id": snapshot["version_id"]},
            {"$set": {key: value for key, value in snapshot.items() if key != "version_id"}},
            upsert=True,
        )
        stored = collection.count_documents({"snapshot_id": snapshot["version_id"]})
    except PyMongoError as error:
        raise ExportError(f"Atlas write failed: {error}") from error

    if stored != len(alerts):
        raise ExportError(f"Atlas holds {stored} records but the snapshot has {len(alerts)}")

    return plan | {"written": written, "removed": removed.deleted_count, "stored": stored}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=settings.DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for key, value in export_snapshot(args.database, args.dry_run).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
