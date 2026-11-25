"""Draft fields from page text using the same AI provider settings as the API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.pipeline import settings
from src.pipeline.extract.api_map import make_record_id
from src.pipeline.models import DraftAlert

logger = logging.getLogger(__name__)

_PROMPT = (
    "Extract one medicine safety notice as JSON with keys: "
    "product_name, source_country, manufacturer, distributor, "
    "publish_date (YYYY-MM-DD or null), reason, more_info. "
    "Use null when unknown. Return JSON only.\n\nTEXT:\n"
)


def draft_from_page_text(
    *,
    text: str,
    source_id: str,
    source_org: str,
    source_url: str,
    raw_path: str | None = None,
) -> DraftAlert:
    extracted = _generate(text)
    product = extracted.get("product_name")
    if isinstance(product, str):
        product = product.strip() or None

    return DraftAlert(
        record_id=make_record_id(source_id, product or "", source_url),
        source_id=source_id,
        source_org=source_org,
        source_url=source_url,
        product_name=product,
        source_country=extracted.get("source_country"),
        manufacturer=extracted.get("manufacturer"),
        distributor=extracted.get("distributor"),
        publish_date=extracted.get("publish_date"),
        reason=extracted.get("reason"),
        more_info=extracted.get("more_info"),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        extraction_method="langextract_ai",
        raw_path=raw_path,
    )


def _generate(text: str) -> dict:
    clipped = text[: settings.extract_max_chars()]
    prompt = _PROMPT + clipped
    from apps.api.services import ai_providers

    _provider, payload = ai_providers.generate_json_with_failover(
        prompt,
        timeout=settings.extract_timeout(),
        max_output_tokens=settings.extract_max_tokens(),
    )
    return payload
