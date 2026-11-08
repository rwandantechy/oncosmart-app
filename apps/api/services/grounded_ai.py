"""Model-backed explanation service with strict evidence boundaries.

Generation runs through whichever provider ``AI_PROVIDER`` selects. Every path
falls back to snapshot-derived output, so answers never depend on a model.
Prompts live in :mod:`apps.api.core.prompts`, response copy in
:mod:`apps.api.core.content`, and keyword rules in :mod:`apps.api.core.rules`.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..core import content, prompts, rules, settings
from .ai_providers import ProviderError, active_provider, record_outcome

logger = logging.getLogger(__name__)

ASSISTANT = content.ASSISTANT
PROVIDERS = content.PROVIDERS


class GroundedExplanation(BaseModel):
    what_happened: str = Field(min_length=1, max_length=settings.EXPLANATION_FIELD_MAX)
    why_it_matters: str = Field(min_length=1, max_length=settings.EXPLANATION_FIELD_MAX)
    what_to_do_next: str = Field(min_length=1, max_length=settings.EXPLANATION_FIELD_MAX)
    limitations: list[str] = Field(min_length=1, max_length=settings.LIMITATIONS_MAX)


class ResearchAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=settings.ANSWER_MAX)
    evidence_used: list[str] = Field(max_length=settings.EVIDENCE_ITEMS_MAX)
    limitations: list[str] = Field(min_length=1, max_length=settings.LIMITATIONS_MAX)


def _ranking(counts: Counter[str], limit: int | None = None) -> str:
    entries = counts.most_common(limit) if limit else counts.most_common()
    return ASSISTANT["ranking_separator"].join(
        ASSISTANT["ranking_entry"].format(name=name, count=count) for name, count in entries
    )


def _count(records: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(row.get(field) or content.MISSING["value"] for row in records)


def _latest_notices(records: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    """Answer "what is new" questions directly from publication dates."""
    latest = sorted(records, key=lambda row: row.get("publish_date") or "", reverse=True)
    lines = "\n".join(
        ASSISTANT["latest_line"].format(
            date=row.get("publish_date") or content.LATEST_MISSING["date"],
            product=row.get("product_name") or content.LATEST_MISSING["product"],
            reason=row.get("reason") or content.LATEST_MISSING["reason"],
            regulator=row.get("source_org") or content.LATEST_MISSING["regulator"],
        )
        for row in latest[: settings.LATEST_RECORD_LIMIT]
    )
    return {
        "enabled": False,
        "provider": PROVIDERS["snapshot_fallback"],
        "answer": ASSISTANT["latest_answer"].format(
            end_date=summary["publication_end"] or content.MISSING["unspecified_date"],
            lines=lines,
        ),
        "evidence_used": [ASSISTANT["latest_evidence"]],
        "limitations": [
            text.format(
                start_date=summary["publication_start"] or content.MISSING["start_date"],
                end_date=summary["publication_end"] or content.MISSING["end_date"],
            )
            for text in ASSISTANT["latest_limitations"]
        ],
    }


def _snapshot_answer(
    question: str,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Direct snapshot calculation used whenever the model cannot be relied on."""
    topic = rules.fallback_topic(question)
    if topic == "regulator":
        answer = ASSISTANT["regulator_answer"].format(
            records=summary["records"], ranking=_ranking(_count(records, "source_org"))
        )
        evidence = ASSISTANT["regulator_evidence"]
    elif topic == "country":
        answer = ASSISTANT["country_answer"].format(
            records=summary["records"], ranking=_ranking(_count(records, "source_country"))
        )
        evidence = ASSISTANT["country_evidence"]
    elif topic == "product":
        answer = ASSISTANT["product_answer"].format(
            ranking=_ranking(_count(records, "product_name"), settings.TOP_PRODUCTS_LIMIT)
        )
        evidence = ASSISTANT["product_evidence"]
    else:
        answer = ASSISTANT["no_answer"]
        evidence = ASSISTANT["snapshot_evidence"]
    return {
        "enabled": False,
        "provider": PROVIDERS["snapshot_fallback"],
        "answer": answer,
        "evidence_used": [evidence],
        "limitations": list(ASSISTANT["fallback_limitations"]),
    }


def answer_research_question(
    question: str,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    question_lower = question.lower()
    if rules.match_keywords(question_lower, rules.LATEST_QUESTION_TERMS):
        return _latest_notices(records, summary)

    if not settings.ai_enabled():
        return {
            "enabled": False,
            "provider": PROVIDERS["unavailable"],
            "answer": ASSISTANT["disabled_answer"],
            "evidence_used": [ASSISTANT["snapshot_evidence"]],
            "limitations": list(ASSISTANT["disabled_limitations"]),
        }

    evidence = {"snapshot": summary, "records": records[: settings.EVIDENCE_RECORD_LIMIT]}
    prompt = prompts.RESEARCH_ANSWER.format(
        question=question,
        evidence=json.dumps(evidence, ensure_ascii=False),
    )
    provider = active_provider()
    try:
        payload = provider.generate_json(
            prompt,
            timeout=provider.ask_timeout,
            max_output_tokens=settings.ASK_OUTPUT_TOKENS,
        )
    except ProviderError as exc:
        record_outcome(provider, False)
        logger.warning("Research answer fell back to the snapshot (%s): %s", provider.name, exc)
        return _snapshot_answer(question_lower, records, summary)

    try:
        parsed = ResearchAnswer.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Research answer had an unusable shape (%s): %s", provider.name, exc)
        return _snapshot_answer(question_lower, records, summary)

    record_outcome(provider, True)
    return {
        "enabled": True,
        "provider": provider.name,
        "model": provider.model,
        **parsed.model_dump(),
    }


def deterministic_explanation(record: dict[str, Any]) -> dict[str, Any]:
    """Source-faithful explanation assembled without a model."""
    reason = record.get("reason") or content.MISSING["reason"]
    return {
        "enabled": False,
        "provider": PROVIDERS["deterministic"],
        "what_happened": content.EXPLANATION["what_happened"].format(
            regulator=record.get("source_org") or content.MISSING["regulator"],
            product=record.get("product_name") or content.MISSING["product"],
            date=record.get("publish_date") or content.MISSING["date"],
            reason=reason,
        ),
        "why_it_matters": rules.significance_for(reason),
        "what_to_do_next": content.EXPLANATION["what_to_do_next"],
        "limitations": list(content.EXPLANATION["limitations"]),
        "evidence": record,
    }


def explain_alert_record(record: dict[str, Any]) -> dict[str, Any]:
    if not settings.ai_enabled():
        return deterministic_explanation(record)

    evidence = {key: record.get(key) for key in rules.EXPLANATION_EVIDENCE_FIELDS}
    prompt = prompts.ALERT_EXPLANATION.format(evidence=json.dumps(evidence, ensure_ascii=False))
    provider = active_provider()
    fallback = deterministic_explanation(record) | {
        "provider": PROVIDERS["deterministic_fallback"],
        "message": content.EXPLANATION["model_unavailable"],
    }
    try:
        payload = provider.generate_json(
            prompt,
            timeout=provider.explain_timeout,
            max_output_tokens=settings.EXPLAIN_OUTPUT_TOKENS,
        )
    except ProviderError as exc:
        record_outcome(provider, False)
        logger.warning("Explanation fell back to deterministic text (%s): %s", provider.name, exc)
        return fallback

    try:
        parsed = GroundedExplanation.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Explanation had an unusable shape (%s): %s", provider.name, exc)
        return fallback

    record_outcome(provider, True)
    return {
        "enabled": True,
        "provider": provider.name,
        "model": provider.model,
        **parsed.model_dump(),
        "evidence": record,
    }
