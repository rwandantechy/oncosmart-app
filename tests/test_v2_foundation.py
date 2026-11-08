import sqlite3
from pathlib import Path

import pytest

from apps.api.services.grounded_ai import deterministic_explanation
from integrations.v1.import_snapshot import import_snapshot

SOURCE_DB = Path(__file__).parents[1] / "src" / "data" / "recalls.db"


def source_metadata():
    with sqlite3.connect(SOURCE_DB) as connection:
        return connection.execute(
            "SELECT COUNT(*), MIN(publish_date), MAX(publish_date), MAX(scraped_at) "
            "FROM recalls"
        ).fetchone()


def test_import_preserves_records_and_records_metadata(tmp_path):
    destination = tmp_path / "v2.db"

    result = import_snapshot(SOURCE_DB, destination)
    source_count, source_min_date, source_max_date, latest_scraped_at = source_metadata()

    assert result["row_count"] == source_count
    with sqlite3.connect(destination) as connection:
        snapshot = connection.execute(
            "SELECT row_count, status, source_min_date, source_max_date, "
            "latest_scraped_at, validation_status, import_status FROM snapshots"
        ).fetchone()
        assert snapshot == (
            source_count,
            "active",
            source_min_date,
            source_max_date,
            latest_scraped_at,
            "validated",
            "active",
        )
        assert connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == source_count
        assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1


def test_failed_validation_does_not_replace_trusted_snapshot(tmp_path):
    destination = tmp_path / "v2.db"
    import_snapshot(SOURCE_DB, destination)
    invalid_source = tmp_path / "invalid.db"
    with sqlite3.connect(invalid_source) as connection:
        connection.execute("CREATE TABLE recalls (record_id TEXT)")

    with pytest.raises(ValueError, match="missing columns"):
        import_snapshot(invalid_source, destination)

    source_count, _, _, _ = source_metadata()
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == source_count
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_deterministic_explanation_identifies_counterfeit_notice():
    explanation = deterministic_explanation({
        "product_name": "Herceptin",
        "source_org": "FDA",
        "publish_date": "2026-01-02",
        "reason": "Confirmed counterfeit medicine",
    })

    assert explanation["enabled"] is False
    assert explanation["provider"] == "deterministic"
    assert "counterfeit" in explanation["why_it_matters"].lower()
    assert "what_happened" in explanation
    assert "what_to_do_next" in explanation


def test_research_report_is_snapshot_derived(workspace_client):
    response = workspace_client.get("/api/insights/research")

    assert response.status_code == 200
    body = response.json()
    assert body["scope"]["records"] == 139
    assert body["scope"]["earliest"] == "2020-01-06"
    assert body["scope"]["latest"] == "2026-03-12"
    assert sum(item["records"] for item in body["notice_categories"]) == 139
