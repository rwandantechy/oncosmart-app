"""Snapshot-derived analysis behind the research workspace.

Every number here is a direct count over the imported records. Nothing is
modelled, estimated, or projected.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from ..core import content, rules, settings
from ..db import snapshot

SNAPSHOT_QUERY = (
    "SELECT version_id, source_checksum, imported_at, row_count, status, "
    "source_min_date, source_max_date, latest_scraped_at, validation_status, import_status "
    "FROM snapshots ORDER BY imported_at DESC LIMIT 1"
)

LATEST_RUN_QUERY = (
    "SELECT status, completed_at, validation_errors FROM import_runs "
    "ORDER BY started_at DESC LIMIT 1"
)

SUMMARY_QUERY = (
    "SELECT COUNT(*) AS total, COUNT(DISTINCT source_org) AS regulators, "
    "COUNT(DISTINCT source_country) AS countries, "
    "MIN(publish_date) AS earliest_publication, "
    "MAX(publish_date) AS latest_publication, MAX(scraped_at) AS latest_collection "
    "FROM alerts"
)

SOURCES_QUERY = (
    "SELECT source_org AS reporting_regulator, source_country AS country_in_source_record, "
    "COUNT(*) AS records "
    "FROM alerts GROUP BY source_org, source_country ORDER BY records DESC"
)

TIMELINE_QUERY = (
    "SELECT substr(publish_date, 1, 7) AS month, COUNT(*) AS records "
    "FROM alerts WHERE publish_date IS NOT NULL GROUP BY month ORDER BY month"
)

BRIEF_QUERY = "SELECT product_name, reason, publish_date, source_org FROM alerts"

IMPORT_FAILED = "failed"
SNAPSHOT_ACTIVE = "active"
SNAPSHOT_VALIDATED = "validated"


def publication_range(records: list[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    """Earliest and latest publication date present in the given records."""
    dates = [record["publish_date"] for record in records if record.get("publish_date")]
    return min(dates, default=None), max(dates, default=None)


def _availability(metadata: dict[str, Any], latest_run: dict[str, Any] | None) -> str:
    if latest_run and latest_run["status"] == IMPORT_FAILED:
        return content.AVAILABILITY["import_failed"]
    if (
        metadata["status"] == SNAPSHOT_ACTIVE
        and metadata["validation_status"] == SNAPSHOT_VALIDATED
    ):
        return content.AVAILABILITY["available"]
    if metadata["import_status"] == IMPORT_FAILED:
        return content.AVAILABILITY["import_failed"]
    return content.AVAILABILITY["awaiting_validation"]


def dataset() -> dict[str, Any] | None:
    """Provenance and validation state of the snapshot being served."""
    with snapshot.connection() as db:
        found = db.execute(SNAPSHOT_QUERY).fetchone()
        latest = db.execute(LATEST_RUN_QUERY).fetchone()
    if found is None:
        return None
    metadata = dict(found)
    latest_run = dict(latest) if latest else None
    return {
        **metadata,
        "availability_status": _availability(metadata, latest_run),
        "last_import_attempt": latest_run,
        "freshness_status": content.DATASET["freshness_status"],
        "collection_status": (
            content.DATASET["collection_recorded"]
            if metadata["latest_scraped_at"]
            else content.DATASET["collection_missing"]
        ),
        "is_currently_monitored": False,
        "label": content.DATASET["label"],
        "source_country_label": content.DATASET["source_country_label"],
    }


def summary() -> dict[str, Any]:
    return snapshot.row(SUMMARY_QUERY) or {}


def sources() -> list[dict[str, Any]]:
    return snapshot.rows(SOURCES_QUERY)


def timeline() -> dict[str, Any]:
    items = snapshot.rows(TIMELINE_QUERY)
    return {
        "items": items,
        "date_basis": content.INSIGHTS["timeline_date_basis"],
        "records_in_full_range": sum(item["records"] for item in items),
        "range_start": items[0]["month"] if items else None,
        "range_end": items[-1]["month"] if items else None,
    }


def completeness() -> list[dict[str, Any]]:
    """How many records carry each field, and how many carry a usable value."""
    with snapshot.connection() as db:
        total = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        results = []
        for field in rules.COMPLETENESS_FIELDS:
            present = db.execute(
                f"SELECT COUNT(*) FROM alerts WHERE {field} IS NOT NULL AND trim({field}) != ''"
            ).fetchone()[0]
            if field == rules.DATE_FIELD:
                valid = db.execute(
                    f"SELECT COUNT(*) FROM alerts WHERE {rules.DATE_FIELD} GLOB ?",
                    (rules.DATE_GLOB,),
                ).fetchone()[0]
            else:
                valid = present
            results.append({"field": field, "present": present, "valid": valid, "total": total})
    return results


def research_brief() -> dict[str, Any]:
    """Keyword-grouped notice counts, frequent products, and publication years."""
    records = snapshot.rows(BRIEF_QUERY)
    earliest, latest = publication_range(records)

    categories = {name: 0 for name, _ in rules.NOTICE_CATEGORIES}
    categories[rules.UNCLASSIFIED_CATEGORY] = 0
    products: Counter[str] = Counter()
    years: Counter[str] = Counter()
    for record in records:
        categories[rules.categorise_notice(record.get("reason") or "")] += 1
        products[(record.get("product_name") or content.MISSING["value"]).strip()] += 1
        date = record.get("publish_date") or ""
        if len(date) >= 4 and date[:4].isdigit():
            years[date[:4]] += 1

    return {
        "scope": {
            "records": len(records),
            "date_basis": content.INSIGHTS["research_date_basis"],
            "earliest": earliest,
            "latest": latest,
        },
        "notice_categories": [
            {"category": category, "records": count} for category, count in categories.items()
        ],
        "top_products": [
            {"product": product, "records": count}
            for product, count in sorted(products.items(), key=lambda item: (-item[1], item[0]))[
                : settings.TOP_PRODUCTS_LIMIT
            ]
        ],
        "publication_years": [{"year": year, "records": years[year]} for year in sorted(years)],
        "method_note": content.INSIGHTS["method_note"],
    }
