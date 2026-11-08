"""Queries over the published regulator notices in the active snapshot."""

from __future__ import annotations

import csv
import io
from typing import Any

from ..core import rules
from ..db import snapshot
from ..schemas.alerts import AlertFilters

SEARCHABLE = "lower(coalesce(product_name, '') || ' ' || coalesce(reason, ''))"

ALL_COLUMNS = "SELECT * FROM alerts"

EVIDENCE_COLUMNS = (
    "SELECT record_id, source_org, source_country, product_name, publish_date, "
    "scraped_at, reason FROM alerts ORDER BY publish_date DESC"
)

REPORT_QUERY = (
    f"SELECT {', '.join(rules.REPORT_COLUMNS)} FROM alerts ORDER BY publish_date DESC, record_id"
)


def _where(filters: AlertFilters) -> tuple[str, list[Any]]:
    """Build the filter clause with bound parameters only."""
    clauses: list[str] = []
    params: list[Any] = []
    if filters.q:
        clauses.append(f"{SEARCHABLE} LIKE ?")
        params.append(f"%{filters.q.strip().lower()}%")
    if filters.country:
        clauses.append("source_country = ?")
        params.append(filters.country)
    if filters.regulator:
        clauses.append("source_org = ?")
        params.append(filters.regulator)
    if filters.from_date:
        clauses.append("publish_date >= ?")
        params.append(filters.from_date)
    if filters.to_date:
        clauses.append("publish_date <= ?")
        params.append(filters.to_date)
    return (f" WHERE {' AND '.join(clauses)}" if clauses else ""), params


def search(filters: AlertFilters) -> dict[str, Any]:
    """One page of notices, newest publication first."""
    where, params = _where(filters)
    offset = (filters.page - 1) * filters.page_size
    with snapshot.connection() as db:
        total = db.execute(f"SELECT COUNT(*) FROM alerts{where}", params).fetchone()[0]
        found = db.execute(
            f"{ALL_COLUMNS}{where} ORDER BY publish_date DESC, record_id LIMIT ? OFFSET ?",
            [*params, filters.page_size, offset],
        ).fetchall()
    return {
        "items": [dict(row) for row in found],
        "total": total,
        "page": filters.page,
        "page_size": filters.page_size,
    }


def get(record_id: str) -> dict[str, Any] | None:
    return snapshot.row(f"{ALL_COLUMNS} WHERE record_id = ?", (record_id,))


def evidence() -> list[dict[str, Any]]:
    """Every record, trimmed to the fields the assistant is allowed to read."""
    return snapshot.rows(EVIDENCE_COLUMNS)


def report_csv() -> str:
    """The full snapshot as CSV, with a header even when it is empty."""
    records = snapshot.rows(REPORT_QUERY)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(rules.REPORT_COLUMNS)
    writer.writerows([tuple(record.values()) for record in records])
    return output.getvalue()
