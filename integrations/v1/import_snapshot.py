"""Import a validated copy of the V1 SQLite snapshot into the V2 database."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_COLUMNS = {
    "record_id", "source_id", "source_org", "source_url", "product_name",
    "source_country", "manufacturer", "distributor", "publish_date",
    "scraped_at", "reason", "more_info",
}


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(source: Path) -> tuple[list[dict], list[str]]:
    if not source.is_file():
        raise FileNotFoundError(f"Source SQLite file does not exist: {source}")
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'recalls'"
        ).fetchone()
        if table is None:
            raise ValueError("Source database does not contain a recalls table")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(recalls)")}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Source schema is missing columns: {', '.join(sorted(missing))}")
        cursor = conn.execute("SELECT * FROM recalls")
        column_names = [column[0] for column in cursor.description]
        rows = [dict(zip(column_names, row, strict=True)) for row in cursor.fetchall()]
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        for field in ("record_id", "source_id", "source_org", "source_url", "scraped_at"):
            if not str(row.get(field) or "").strip():
                errors.append(f"row {index}: blank required field {field}")
        record_id = str(row.get("record_id") or "")
        if record_id in seen:
            errors.append(f"row {index}: duplicate record_id {record_id}")
        seen.add(record_id)
        parsed = urlparse(str(row.get("source_url") or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"row {index}: invalid source_url")
    return rows, errors


def import_snapshot(source: Path, destination: Path, dry_run: bool = False) -> dict:
    source_checksum = checksum(source) if source.is_file() else ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    snapshot_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{source_checksum[:12]}"
    if dry_run:
        rows, errors = validate(source)
        if errors:
            raise ValueError("Snapshot validation failed:\n" + "\n".join(errors[:20]))
        return {"version_id": snapshot_id, "row_count": len(rows), "dry_run": True}
    with sqlite3.connect(destination) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                version_id TEXT PRIMARY KEY, source_checksum TEXT NOT NULL,
                imported_at TEXT NOT NULL, row_count INTEGER NOT NULL,
                status TEXT NOT NULL, source_min_date TEXT,
                source_max_date TEXT, latest_scraped_at TEXT,
                validation_status TEXT NOT NULL DEFAULT 'awaiting_validation',
                import_status TEXT NOT NULL DEFAULT 'awaiting_validation'
            );
            CREATE TABLE IF NOT EXISTS import_runs (
                run_id TEXT PRIMARY KEY, source_path TEXT NOT NULL,
                source_checksum TEXT NOT NULL, started_at TEXT NOT NULL,
                completed_at TEXT, status TEXT NOT NULL,
                row_count INTEGER, validation_errors TEXT
            );
            CREATE TABLE IF NOT EXISTS alerts (
                record_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                source_org TEXT NOT NULL, source_url TEXT NOT NULL,
                product_name TEXT, source_country TEXT, manufacturer TEXT,
                distributor TEXT, publish_date TEXT, scraped_at TEXT NOT NULL,
                reason TEXT, more_info TEXT, snapshot_id TEXT NOT NULL
            );
            """
        )
        snapshot_columns = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
        for column, definition in {
            "source_min_date": "TEXT",
            "source_max_date": "TEXT",
            "latest_scraped_at": "TEXT",
            "validation_status": "TEXT NOT NULL DEFAULT 'validated'",
            "import_status": "TEXT NOT NULL DEFAULT 'active'",
        }.items():
            if column not in snapshot_columns:
                conn.execute(f"ALTER TABLE snapshots ADD COLUMN {column} {definition}")
        conn.execute(
            "INSERT OR REPLACE INTO import_runs "
            "(run_id, source_path, source_checksum, started_at, status) "
            "VALUES (?, ?, ?, ?, 'awaiting_validation')",
            (snapshot_id, str(source), source_checksum, started_at),
        )
        rows, errors = validate(source)
        if errors:
            message = "\n".join(errors[:20])
            conn.execute(
                "UPDATE import_runs SET completed_at = ?, status = 'failed', "
                "validation_errors = ? WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), message, snapshot_id),
            )
            conn.commit()
            raise ValueError("Snapshot validation failed:\n" + message)
        dates = [row["publish_date"] for row in rows if row.get("publish_date")]
        scraped = [row["scraped_at"] for row in rows if row.get("scraped_at")]
        with conn:
            try:
                conn.execute("DROP TABLE IF EXISTS alerts_staging")
                conn.execute("CREATE TABLE alerts_staging AS SELECT * FROM alerts WHERE 0")
                conn.executemany(
                    """INSERT INTO alerts_staging VALUES
                    (:record_id, :source_id, :source_org, :source_url, :product_name,
                     :source_country, :manufacturer, :distributor, :publish_date,
                     :scraped_at, :reason, :more_info, :snapshot_id)""",
                    [{**row, "snapshot_id": snapshot_id} for row in rows],
                )
                staged_count = conn.execute("SELECT COUNT(*) FROM alerts_staging").fetchone()[0]
                if staged_count != len(rows):
                    raise ValueError("Staged row count does not match validated row count")
                conn.execute("DELETE FROM alerts")
                conn.execute("INSERT INTO alerts SELECT * FROM alerts_staging")
                conn.execute("DELETE FROM snapshots WHERE status = 'active'")
                conn.execute(
                    """INSERT INTO snapshots
                    (version_id, source_checksum, imported_at, row_count, status,
                     source_min_date, source_max_date, latest_scraped_at,
                     validation_status, import_status)
                    VALUES (?, ?, ?, ?, 'active', ?, ?, ?, 'validated', 'active')""",
                    (
                        snapshot_id, source_checksum,
                        datetime.now(timezone.utc).isoformat(), len(rows),
                        min(dates) if dates else None, max(dates) if dates else None,
                        max(scraped) if scraped else None,
                    ),
                )
                conn.execute(
                    "UPDATE import_runs SET completed_at = ?, status = 'active', row_count = ? "
                    "WHERE run_id = ?",
                    (datetime.now(timezone.utc).isoformat(), len(rows), snapshot_id),
                )
                conn.execute("DROP TABLE alerts_staging")
            except (OSError, sqlite3.Error, ValueError):
                conn.execute("DROP TABLE IF EXISTS alerts_staging")
                raise
    return {"version_id": snapshot_id, "row_count": len(rows), "dry_run": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("apps/api/data/v2.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(import_snapshot(args.source, args.destination, args.dry_run))


if __name__ == "__main__":
    main()
