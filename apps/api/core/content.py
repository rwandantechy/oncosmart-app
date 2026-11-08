"""Every string the API returns to a client.

Keeping response copy, error details, and standing limitation notices here means
wording can be reviewed and changed without touching request handling or the
grounding logic. Templates use ``str.format`` placeholders.
"""

from __future__ import annotations

# --- Service metadata -------------------------------------------------------

STATUS_OK = "ok"

API_TITLE = "EveryDoseMatters V2 API"
API_VERSION = "0.1.0"

# --- Error details ----------------------------------------------------------
# These strings are returned to the browser. They must never name vendors,
# hosts, environment variables, or other internals.

ERRORS = {
    "no_snapshot": "These notices are not available right now.",
    "no_active_snapshot": "These notices are not available right now.",
    "alert_not_found": "This notice was not found.",
    "invalid_request": "The request could not be accepted: {reason}",
    "auth_not_configured": (
        "The research workspace is temporarily unavailable. Please try again shortly."
    ),
    "auth_store_unavailable": (
        "The research workspace is temporarily unavailable. Please try again shortly."
    ),
    "signup_closed": "New accounts are not being created.",
    "email_taken": "An account with this email already exists.",
    "bad_credentials": "Email or password is incorrect.",
    "sign_in_required": "Sign in to use the research workspace.",
    "session_expired": "Your session has expired. Sign in again.",
    "account_not_found": "This account no longer exists.",
    "wrong_password": "Your current password is incorrect.",
    "password_unchanged": "Choose a new password that is different from the current one.",
    "name_too_short": "Name must contain at least {minimum} characters.",
}

# How a field path and message are joined in an invalid-request detail.
FIELD_ERROR = "{field} — {message}"
FIELD_ERROR_SEPARATOR = "; "

# --- Dataset descriptions ---------------------------------------------------

AVAILABILITY = {
    "available": "available",
    "import_failed": "import failed",
    "awaiting_validation": "awaiting validation",
}

DATASET = {
    "freshness_status": "historical snapshot",
    "label": "Historical snapshot — not current surveillance",
    "source_country_label": "Country value recorded in the source alert",
    "collection_recorded": (
        "last recorded collection time is available; V1 does not record run-level success"
    ),
    "collection_missing": "collection time not recorded",
}

# --- Insight labels ---------------------------------------------------------

INSIGHTS = {
    "timeline_date_basis": "Publication month from publish_date",
    "research_date_basis": "Publication date",
    "method_note": (
        "Categories are keyword-based indicators derived from the stored reason field. "
        "They are not clinical classifications or measures of risk."
    ),
}

# --- Deterministic explanation ----------------------------------------------

MISSING = {
    "product": "This product",
    "regulator": "The regulator",
    "date": "an unspecified date",
    "reason": "The notice does not give a reason in the imported record.",
    "value": "Not provided",
    "start_date": "an unspecified start date",
    "end_date": "an unspecified end date",
    "unspecified_date": "an unspecified date",
}

LATEST_MISSING = {
    "date": "Date not provided",
    "product": "Product not provided",
    "reason": "Reason not provided",
    "regulator": "Regulator not provided",
}

EXPLANATION = {
    "what_happened": (
        "{regulator} reported an issue involving {product}. "
        "The notice was published on {date}. It describes the issue as: {reason}"
    ),
    "what_to_do_next": (
        "Read the original notice for the complete details. If you are concerned about a "
        "medicine, speak with a pharmacist or healthcare professional before making "
        "treatment decisions."
    ),
    "limitations": [
        "This notice does not tell us whether every product with this name is affected.",
        "The imported record may not include every detail from the original notice.",
    ],
    "model_unavailable": "A generated summary was not available, so this text comes from the notice on file.",
}

# --- Research assistant -----------------------------------------------------

ASSISTANT = {
    "latest_answer": (
        "The most recently published notices on file go through {end_date}:\n"
        "{lines}"
    ),
    "latest_line": "- {date} — {product}: {reason} ({regulator})",
    "latest_evidence": (
        "Publication dates, product names, reasons, and reporting regulators from the "
        "notices on file."
    ),
    "latest_limitations": [
        "These notices cover {start_date} through {end_date}. They do not tell you what is "
        "happening today.",
        "Dates shown are when the notice was published, not when a medicine was used.",
    ],
    "disabled_answer": (
        "This question helper is not available right now. Review the notices, charts, "
        "and download on this workspace instead."
    ),
    "disabled_limitations": [
        "No generated answer was produced.",
        "These notices are historical. They do not measure how common a problem is now, "
        "or current risk.",
    ],
    "snapshot_evidence": "The notices on file can be reviewed and downloaded.",
    "regulator_answer": (
        "Among {records} notices on file, these reporting regulators appear:\n{ranking}"
    ),
    "regulator_evidence": "Reporting regulators counted from every notice on file.",
    "country_answer": (
        "Among {records} notices on file, these countries are named:\n{ranking}"
    ),
    "country_evidence": "Countries named in the notices, as written in the original records.",
    "product_answer": "These products appear most often in the notices on file:\n{ranking}",
    "product_evidence": "Product names counted from the notices on file.",
    "no_answer": (
        "I could not answer that from the notices on file. Try asking about products, "
        "regulators, countries named in the notices, or publication dates."
    ),
    "fallback_limitations": [
        "A generated answer was not available, so this reply is counted from the notices "
        "on file.",
        "These notices are historical. They do not measure how common a problem is now, "
        "or current risk.",
    ],
    "ranking_entry": "- {name}: {count}",
    "ranking_separator": "\n",
}

# --- Provider labels the interface recognises verbatim -----------------------

PROVIDERS = {
    "deterministic": "deterministic",
    "deterministic_fallback": "deterministic-fallback",
    "snapshot_fallback": "snapshot-fallback",
    "unavailable": "unavailable",
}
