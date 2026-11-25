"""Environment-backed API configuration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

GEMINI = "gemini"
OPENROUTER = "openrouter"
PROVIDER_NAMES = (GEMINI, OPENROUTER)

DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
# gemini-2.5-flash is closed to new API keys and returns 404 on generateContent.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"

_TRUTHY = {"1", "true", "yes", "on"}


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def _number(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s is not a number; using %s", name, default)
        return default


def _whole(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s is not an integer; using %s", name, default)
        return default


@dataclass(frozen=True)
class GeminiSettings:
    """Connection details for the Google Gemini generative language API."""

    url: str
    model: str
    api_key: str
    thinking_budget: int
    ask_timeout: float
    explain_timeout: float
    health_timeout: float
    name: str = GEMINI

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class OpenRouterSettings:
    """Connection details for the OpenRouter OpenAI-compatible chat API."""

    url: str
    model: str
    api_key: str
    ask_timeout: float
    explain_timeout: float
    health_timeout: float
    site_url: str
    app_name: str
    name: str = OPENROUTER

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def ai_enabled() -> bool:
    """Whether model-generated output is permitted at all in this environment."""
    return _flag("V2_AI_ENABLED", "true")


def provider_name() -> str:
    """Primary provider from ``AI_PROVIDER`` (first entry of the failover chain)."""
    chain = provider_chain_names()
    return chain[0] if chain else GEMINI


def provider_chain_names() -> list[str]:
    """Ordered provider names for failover.

    Prefer ``AI_PROVIDERS=gemini,openrouter``. Otherwise use ``AI_PROVIDER`` plus
    optional ``AI_FALLBACK_PROVIDER``.
    """
    raw_list = os.getenv("AI_PROVIDERS", "").strip()
    if raw_list:
        names = [part.strip().lower() for part in raw_list.split(",") if part.strip()]
    else:
        primary = os.getenv("AI_PROVIDER", GEMINI).strip().lower() or GEMINI
        fallback = os.getenv("AI_FALLBACK_PROVIDER", "").strip().lower()
        names = [primary]
        if fallback and fallback != primary:
            names.append(fallback)

    ordered: list[str] = []
    for name in names:
        if name not in PROVIDER_NAMES:
            logger.warning(
                "Ignoring unknown AI provider %r; expected one of %s",
                name,
                ", ".join(PROVIDER_NAMES),
            )
            continue
        if name not in ordered:
            ordered.append(name)
    return ordered or [GEMINI]


def gemini_settings() -> GeminiSettings:
    return GeminiSettings(
        url=os.getenv("GEMINI_API_URL", DEFAULT_GEMINI_URL).rstrip("/"),
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        thinking_budget=_whole("GEMINI_THINKING_BUDGET", 0),
        ask_timeout=_number("AI_ASK_TIMEOUT", 25.0),
        explain_timeout=_number("AI_EXPLAIN_TIMEOUT", 30.0),
        health_timeout=_number("AI_HEALTH_TIMEOUT", 1.5),
    )


def openrouter_settings() -> OpenRouterSettings:
    return OpenRouterSettings(
        url=os.getenv("OPENROUTER_API_URL", DEFAULT_OPENROUTER_URL).rstrip("/"),
        model=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
        api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        ask_timeout=_number("AI_ASK_TIMEOUT", 25.0),
        explain_timeout=_number("AI_EXPLAIN_TIMEOUT", 30.0),
        health_timeout=_number("AI_HEALTH_TIMEOUT", 1.5),
        site_url=os.getenv(
            "OPENROUTER_SITE_URL",
            os.getenv("V2_PUBLIC_APP_URL", DEFAULT_PUBLIC_APP_URL),
        )
        .strip()
        .rstrip("/"),
        app_name=os.getenv("OPENROUTER_APP_NAME", "EveryDoseMatters"),
    )


def health_cache_seconds() -> float:
    """How long a provider reachability probe may be reused by ``/api/health``."""
    return _number("AI_HEALTH_CACHE_SECONDS", 30.0)


# --- Storage and transport --------------------------------------------------

_API_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _API_ROOT.parent.parent
DEFAULT_DB = _API_ROOT / "data" / "v2.db"
DEFAULT_DRUGS_LIST_CANDIDATES = (
    _REPO_ROOT / "src" / "data" / "nci_oncology_drugs.json",
    _API_ROOT / "data" / "nci_oncology_drugs.json",
)
DEFAULT_DRUGS_CATALOG_CANDIDATES = (
    _REPO_ROOT / "src" / "data" / "nci_oncology_drugs_catalog.json",
    _API_ROOT / "data" / "nci_oncology_drugs_catalog.json",
)
DEFAULT_CORS_ORIGINS = "http://localhost:5173,https://oncosmart.vercel.app"
DEFAULT_PUBLIC_APP_URL = "https://oncosmart.vercel.app/"
NCI_DRUGS_SOURCE_URL = os.getenv(
    "V2_NCI_DRUGS_SOURCE_URL",
    "https://www.cancer.gov/about-cancer/treatment/drugs/cancer-drugs",
)
NCI_DRUG_INFO_URL = os.getenv(
    "V2_NCI_DRUG_INFO_URL",
    "https://www.cancer.gov/about-cancer/treatment/drugs/{slug}",
)

# Auth can rotate a session with PATCH; everything else is GET or POST.
CORS_METHODS = tuple(
    os.getenv("V2_CORS_METHODS", "GET,POST,PUT,PATCH,DELETE").split(",")
)
CORS_HEADERS = tuple(os.getenv("V2_CORS_HEADERS", "*").split(","))
# The CSV export is fetched with an access token rather than followed as a
# link, so the browser needs permission to read the filename the API chose.
CORS_EXPOSE_HEADERS = tuple(
    os.getenv("V2_CORS_EXPOSE_HEADERS", "Content-Disposition").split(",")
)


def database_path() -> Path:
    """Location of the imported V2 snapshot."""
    return Path(os.getenv("V2_DATABASE", DEFAULT_DB))


def drugs_list_path() -> Path:
    """NCI oncology drug-name list used for matching scrapers."""
    override = os.getenv("V2_DRUGS_LIST", "").strip()
    if override:
        return Path(override)
    for candidate in DEFAULT_DRUGS_LIST_CANDIDATES:
        if candidate.is_file():
            return candidate
    return DEFAULT_DRUGS_LIST_CANDIDATES[0]


def drugs_catalog_path() -> Path:
    """NCI drug catalog with official page URLs for the Drug list page."""
    override = os.getenv("V2_DRUGS_CATALOG", "").strip()
    if override:
        return Path(override)
    for candidate in DEFAULT_DRUGS_CATALOG_CANDIDATES:
        if candidate.is_file():
            return candidate
    # Prefer a sibling of the token list when the catalog has not been written yet.
    return drugs_list_path().with_name("nci_oncology_drugs_catalog.json")


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API."""
    raw = os.getenv("V2_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def public_app_url() -> str:
    """Public web app URL shown when someone opens the API root in a browser."""
    return os.getenv("V2_PUBLIC_APP_URL", DEFAULT_PUBLIC_APP_URL).strip() or DEFAULT_PUBLIC_APP_URL


# --- Request shape ----------------------------------------------------------
# Read once at import because they define the API contract. Set them in .env
# before starting the server rather than per request.

PAGE_SIZE_DEFAULT = _whole("API_PAGE_SIZE_DEFAULT", 20)
PAGE_SIZE_MAX = _whole("API_PAGE_SIZE_MAX", 100)
SEARCH_MAX_LENGTH = _whole("API_SEARCH_MAX_LENGTH", 100)
COUNTRY_MAX_LENGTH = _whole("API_COUNTRY_MAX_LENGTH", 100)
REGULATOR_MAX_LENGTH = _whole("API_REGULATOR_MAX_LENGTH", 200)
DATE_MAX_LENGTH = _whole("API_DATE_MAX_LENGTH", 10)
QUESTION_MAX_LENGTH = _whole("API_QUESTION_MAX_LENGTH", 1000)

# --- Model output bounds ----------------------------------------------------

ASK_OUTPUT_TOKENS = _whole("AI_ASK_OUTPUT_TOKENS", 1024)
EXPLAIN_OUTPUT_TOKENS = _whole("AI_EXPLAIN_OUTPUT_TOKENS", 2048)
EXPLANATION_FIELD_MAX = _whole("AI_EXPLANATION_FIELD_MAX", 1200)
ANSWER_MAX = _whole("AI_ANSWER_MAX", 3000)
LIMITATIONS_MAX = _whole("AI_LIMITATIONS_MAX", 8)
EVIDENCE_ITEMS_MAX = _whole("AI_EVIDENCE_ITEMS_MAX", 10)

# --- Analysis and evidence shaping ------------------------------------------

QUESTION_TERM_LIMIT = _whole("AI_QUESTION_TERM_LIMIT", 8)
QUESTION_MIN_TERM_LENGTH = _whole("AI_QUESTION_MIN_TERM_LENGTH", 2)
EVIDENCE_RECORD_LIMIT = _whole("AI_EVIDENCE_RECORD_LIMIT", 8)
LATEST_RECORD_LIMIT = _whole("AI_LATEST_RECORD_LIMIT", 5)
TOP_PRODUCTS_LIMIT = _whole("API_TOP_PRODUCTS_LIMIT", 10)
REPORT_FILENAME = os.getenv("API_REPORT_FILENAME", "everydosematters-research-records.csv")

# --- Authentication ---------------------------------------------------------

JWT_ALGORITHM = os.getenv("V2_JWT_ALGORITHM", "HS256")
EMAIL_FIELD = "email"
TOKEN_TYPE = "bearer"
# The scheme name as it appears in Authorization and WWW-Authenticate headers.
AUTH_SCHEME = "Bearer"
TOKEN_TTL_HOURS = _number("V2_TOKEN_TTL_HOURS", 8.0)
MONGO_TIMEOUT_MS = _whole("MONGODB_TIMEOUT_MS", 5000)
USERS_COLLECTION = os.getenv("MONGODB_USERS_COLLECTION", "users")
ALERTS_COLLECTION = os.getenv("MONGODB_ALERTS_COLLECTION", "alerts")
SNAPSHOTS_COLLECTION = os.getenv("MONGODB_SNAPSHOTS_COLLECTION", "snapshots")
REVIEW_COLLECTION = os.getenv("MONGODB_REVIEW_COLLECTION", "review_queue")
DRUGS_COLLECTION = os.getenv("MONGODB_DRUGS_COLLECTION", "oncology_drugs")
DRUGS_META_COLLECTION = os.getenv("MONGODB_DRUGS_META_COLLECTION", "oncology_drugs_meta")
RUNTIME_SETTINGS_COLLECTION = os.getenv(
    "MONGODB_RUNTIME_SETTINGS_COLLECTION", "runtime_settings"
)
DEFAULT_USER_ROLE = os.getenv("V2_DEFAULT_USER_ROLE", "researcher")
ADMIN_ROLE = os.getenv("V2_ADMIN_ROLE", "admin")
NAME_MIN_LENGTH = _whole("V2_NAME_MIN_LENGTH", 2)
NAME_MAX_LENGTH = _whole("V2_NAME_MAX_LENGTH", 120)
PASSWORD_MIN_LENGTH = _whole("V2_PASSWORD_MIN_LENGTH", 8)
PASSWORD_MAX_LENGTH = _whole("V2_PASSWORD_MAX_LENGTH", 128)

# --- GitHub Actions (admin-triggered collection tools) ----------------------

GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_ACTIONS_REF = os.getenv("GITHUB_ACTIONS_REF", "main")
GITHUB_WORKFLOW_WEEKLY_SCRAPE = os.getenv(
    "GITHUB_WORKFLOW_WEEKLY_SCRAPE", "weekly_scrape.yaml"
)
GITHUB_WORKFLOW_DRUG_DATABASE = os.getenv(
    "GITHUB_WORKFLOW_DRUG_DATABASE", "drug_database.yaml"
)
COLLECTION_JOB_COOLDOWN_SECONDS = _number("V2_COLLECTION_JOB_COOLDOWN_SECONDS", 60.0)


def signup_open() -> bool:
    """Public account creation. Closed unless V2_SIGNUP_OPEN is set."""
    return _flag("V2_SIGNUP_OPEN", "false")


def auth_database() -> str:
    return os.getenv("MONGODB_DATABASE", "everydosematters")


def admin_emails() -> set[str]:
    """Emails treated as admin even if the stored role is still researcher."""
    raw = os.getenv("V2_ADMIN_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def github_actions_token() -> str:
    return os.getenv("GITHUB_ACTIONS_TOKEN", "").strip()


def github_actions_repo() -> str:
    """owner/name of the repo that hosts the collection workflows."""
    return os.getenv("GITHUB_ACTIONS_REPO", "").strip()
