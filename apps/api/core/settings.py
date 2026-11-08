"""Environment-backed API configuration.

Values are read on each call rather than frozen at import time so that a process
started with a different ``--env-file`` (and tests that patch the environment)
always see the current configuration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OLLAMA = "ollama"
GEMINI = "gemini"
PROVIDER_NAMES = (OLLAMA, GEMINI)

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
# gemini-2.5-flash is closed to new API keys and returns 404 on generateContent.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"

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
class OllamaSettings:
    """Connection details for a local Ollama daemon."""

    url: str
    model: str
    ask_timeout: float
    explain_timeout: float
    health_timeout: float
    name: str = OLLAMA

    @property
    def configured(self) -> bool:
        return bool(self.url)


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


def ai_enabled() -> bool:
    """Whether model-generated output is permitted at all in this environment."""
    return _flag("V2_AI_ENABLED", "true")


def provider_name() -> str:
    """The configured provider, falling back to local Ollama for unknown values."""
    requested = os.getenv("AI_PROVIDER", OLLAMA).strip().lower()
    if requested in PROVIDER_NAMES:
        return requested
    if requested:
        logger.warning(
            "AI_PROVIDER=%r is not one of %s; using %s",
            requested,
            ", ".join(PROVIDER_NAMES),
            OLLAMA,
        )
    return OLLAMA


def ollama_settings() -> OllamaSettings:
    return OllamaSettings(
        url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        ask_timeout=_number("AI_ASK_TIMEOUT", 12.0),
        explain_timeout=_number("AI_EXPLAIN_TIMEOUT", 45.0),
        health_timeout=_number("AI_HEALTH_TIMEOUT", 0.4),
    )


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


def health_cache_seconds() -> float:
    """How long a provider reachability probe may be reused by ``/api/health``."""
    return _number("AI_HEALTH_CACHE_SECONDS", 30.0)


# --- Storage and transport --------------------------------------------------

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "v2.db"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,https://oncosmart.vercel.app"

# Auth can rotate a session with PATCH; everything else is GET or POST.
CORS_METHODS = tuple(os.getenv("V2_CORS_METHODS", "GET,POST,PATCH").split(","))
CORS_HEADERS = tuple(os.getenv("V2_CORS_HEADERS", "*").split(","))
# The CSV export is fetched with an access token rather than followed as a
# link, so the browser needs permission to read the filename the API chose.
CORS_EXPOSE_HEADERS = tuple(
    os.getenv("V2_CORS_EXPOSE_HEADERS", "Content-Disposition").split(",")
)


def database_path() -> Path:
    """Location of the imported V2 snapshot."""
    return Path(os.getenv("V2_DATABASE", DEFAULT_DB))


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API."""
    raw = os.getenv("V2_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


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
DEFAULT_USER_ROLE = os.getenv("V2_DEFAULT_USER_ROLE", "researcher")
NAME_MIN_LENGTH = _whole("V2_NAME_MIN_LENGTH", 2)
NAME_MAX_LENGTH = _whole("V2_NAME_MAX_LENGTH", 120)
PASSWORD_MIN_LENGTH = _whole("V2_PASSWORD_MIN_LENGTH", 8)
PASSWORD_MAX_LENGTH = _whole("V2_PASSWORD_MAX_LENGTH", 128)


def signup_open() -> bool:
    """Public account creation. Closed unless V2_SIGNUP_OPEN is set."""
    return _flag("V2_SIGNUP_OPEN", "false")


def auth_database() -> str:
    return os.getenv("MONGODB_DATABASE", "everydosematters")
