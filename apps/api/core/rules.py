"""Keyword rules and field lists that shape the snapshot analysis.

These are editorial decisions about how stored text is grouped, not application
logic, so they live apart from the handlers that apply them. Every rule is a
keyword indicator over the imported ``reason`` field; none is a clinical
classification.
"""

from __future__ import annotations

# Columns selected for the CSV export, which are also its header row.
REPORT_COLUMNS = (
    "record_id",
    "source_id",
    "source_org",
    "source_url",
    "product_name",
    "source_country",
    "manufacturer",
    "distributor",
    "publish_date",
    "scraped_at",
    "reason",
    "more_info",
)

# Fields reported by /api/insights/completeness, in display order.
COMPLETENESS_FIELDS = (
    "product_name",
    "source_country",
    "manufacturer",
    "distributor",
    "publish_date",
    "reason",
    "more_info",
)

# Field checked against a strict date shape rather than mere presence.
DATE_FIELD = "publish_date"
DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"

# Notice categories for /api/insights/research, matched in order. The first
# match wins, and anything unmatched lands in UNCLASSIFIED_CATEGORY.
NOTICE_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Counterfeit or falsified", ("counterfeit", "fake", "falsified")),
    ("Recall or withdrawal", ("recall", "withdraw", "recalled")),
    ("Quality or defect", ("quality", "defect", "contamination", "contaminated")),
)
UNCLASSIFIED_CATEGORY = "Other or not classified"

# Significance sentences for the deterministic explanation, matched in order.
SIGNIFICANCE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("counterfeit", "fake"),
        "The notice concerns a product presented as this medicine but identified by the "
        "regulator as counterfeit.",
    ),
    (
        ("recall",),
        "The notice describes a regulatory action involving the product. The original "
        "notice identifies the products and scope involved.",
    ),
    (
        ("quality", "defect"),
        "The notice describes a quality concern. The original notice provides the "
        "product-specific details needed to understand its scope.",
    ),
)
DEFAULT_SIGNIFICANCE = (
    "The significance depends on the product and details described in the original notice."
)

# Questions that are answered directly from the snapshot instead of a model.
LATEST_QUESTION_TERMS = ("recent", "latest", "new alerts", "new notices")

# Question routing for the snapshot fallback, matched in order.
FALLBACK_TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("regulator", ("regulator", "agency")),
    ("country", ("country", "countries")),
    ("product", ("product", "medicine", "alert")),
)

# Record fields passed to the model as explanation evidence.
EXPLANATION_EVIDENCE_FIELDS = (
    "product_name",
    "source_org",
    "source_country",
    "manufacturer",
    "distributor",
    "publish_date",
    "reason",
    "more_info",
    "source_url",
)


def match_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    """Whether any keyword appears in ``text``, compared case-insensitively."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def categorise_notice(reason: str) -> str:
    """The first matching notice category, or the unclassified bucket."""
    for category, keywords in NOTICE_CATEGORIES:
        if match_keywords(reason, keywords):
            return category
    return UNCLASSIFIED_CATEGORY


def significance_for(reason: str) -> str:
    """The significance sentence for a stored notice reason."""
    for keywords, sentence in SIGNIFICANCE_RULES:
        if match_keywords(reason, keywords):
            return sentence
    return DEFAULT_SIGNIFICANCE


def fallback_topic(question: str) -> str | None:
    """Which snapshot calculation answers the question, if any."""
    for topic, keywords in FALLBACK_TOPICS:
        if match_keywords(question, keywords):
            return topic
    return None
