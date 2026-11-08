"""Assembles the evidence a question is allowed to be answered from.

The model never queries the snapshot itself. This module selects the records
and the summary, and :mod:`apps.api.services.grounded_ai` turns them into an
answer that always degrades to a direct snapshot calculation.
"""

from __future__ import annotations

from typing import Any

from ..core import settings
from . import alerts
from .grounded_ai import answer_research_question
from .insights import publication_range


def _terms(question: str) -> list[str]:
    """Words long enough to be worth matching, capped so one question is bounded."""
    return [
        term.lower()
        for term in question.split()
        if len(term) > settings.QUESTION_MIN_TERM_LENGTH
    ][: settings.QUESTION_TERM_LIMIT]


def _matching(records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    if not terms:
        return records
    return [
        record
        for record in records
        if any(
            term in " ".join(str(field or "").lower() for field in record.values())
            for term in terms
        )
    ]


def answer(question: str) -> dict[str, Any]:
    records = alerts.evidence()
    publication_start, publication_end = publication_range(records)
    summary = {
        "records": len(records),
        "publication_start": publication_start,
        "publication_end": publication_end,
        "reporting_regulators": sorted({record["source_org"] for record in records}),
        "recorded_country_values": sorted(
            {record["source_country"] for record in records if record.get("source_country")}
        ),
        "matched_records": len(_matching(records, _terms(question))),
    }
    return answer_research_question(question, records, summary)
