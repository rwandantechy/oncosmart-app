"""Interchangeable JSON-producing model backends with optional failover."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib import error, request

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from ..core import settings
from ..db import mongo

logger = logging.getLogger(__name__)

_JSON_HEADERS = {"Content-Type": "application/json"}

# Reachability is cached so a page that polls /api/health does not probe per call.
_availability_cache: dict[str, tuple[float, bool]] = {}

AI_PREF_ID = "ai_providers"
PROVIDER_LABELS = {
    settings.GEMINI: "Gemini",
    settings.OPENROUTER: "OpenRouter",
}

ProviderConfig = settings.GeminiSettings | settings.OpenRouterSettings


class ProviderError(RuntimeError):
    """A provider is unconfigured, unreachable, or returned unusable output."""


class PreferenceError(RuntimeError):
    """Admin AI preference could not be read or written."""


def clear_availability_cache() -> None:
    """Drop cached reachability results. Used by tests and after config changes."""
    _availability_cache.clear()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict:
    body = json.dumps(payload).encode()
    req = request.Request(url, data=body, headers={**_JSON_HEADERS, **headers}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise ProviderError(f"HTTP {exc.code}: {detail}") from exc


def _reachable(url: str, headers: dict[str, str], timeout: float) -> bool:
    try:
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def _json_object(text: str) -> dict:
    """Models occasionally wrap JSON in prose, so retry on the outermost braces."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


class Provider:
    """Shared surface for the supported model backends."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def ask_timeout(self) -> float:
        return self.config.ask_timeout

    @property
    def explain_timeout(self) -> float:
        return self.config.explain_timeout

    def available(self) -> bool:
        raise NotImplementedError

    def generate_json(self, prompt: str, *, timeout: float, max_output_tokens: int) -> dict:
        raise NotImplementedError


class GeminiProvider(Provider):
    """Google Gemini generateContent, constrained to JSON responses.

    The API key travels in the ``x-goog-api-key`` header rather than the query
    string so it cannot leak through URLs in logs or error messages.
    """

    config: settings.GeminiSettings

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.config.api_key}

    def available(self) -> bool:
        if not self.configured:
            return False
        url = f"{self.config.url}/models/{self.config.model}"
        return _reachable(url, self._headers(), self.config.health_timeout)

    def generate_json(self, prompt: str, *, timeout: float, max_output_tokens: int) -> dict:
        if not self.configured:
            raise ProviderError("GEMINI_API_KEY is not set")

        generation: dict[str, Any] = {
            "temperature": 0,
            "responseMimeType": "application/json",
            "maxOutputTokens": max_output_tokens,
        }
        if self.config.thinking_budget >= 0:
            generation["thinkingConfig"] = {"thinkingBudget": self.config.thinking_budget}

        url = f"{self.config.url}/models/{self.config.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation}
        try:
            body = _post_json(url, payload, self._headers(), timeout)
        except (OSError, ValueError, ProviderError) as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc

        try:
            parts = body["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini returned no candidate content") from exc

        text = "".join(part.get("text", "") for part in parts)
        try:
            return _json_object(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Gemini returned output that is not JSON") from exc


class OpenRouterProvider(Provider):
    """OpenRouter chat completions (OpenAI-compatible), constrained to JSON."""

    config: settings.OpenRouterSettings

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }
        if self.config.site_url:
            headers["HTTP-Referer"] = self.config.site_url
        if self.config.app_name:
            headers["X-Title"] = self.config.app_name
        return headers

    def available(self) -> bool:
        if not self.configured:
            return False
        # /models is public; with a key it confirms auth is accepted.
        return _reachable(
            f"{self.config.url}/models",
            self._headers(),
            self.config.health_timeout,
        )

    def generate_json(self, prompt: str, *, timeout: float, max_output_tokens: int) -> dict:
        if not self.configured:
            raise ProviderError("OPENROUTER_API_KEY is not set")

        payload = {
            "model": self.config.model,
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with a single JSON object only. No markdown.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        try:
            body = _post_json(
                f"{self.config.url}/chat/completions",
                payload,
                self._headers(),
                timeout,
            )
        except (OSError, ValueError, ProviderError) as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc

        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenRouter returned no message content") from exc

        try:
            return _json_object(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenRouter returned output that is not JSON") from exc


def build_provider(name: str) -> Provider:
    if name == settings.GEMINI:
        return GeminiProvider(settings.gemini_settings())
    if name == settings.OPENROUTER:
        return OpenRouterProvider(settings.openrouter_settings())
    raise ProviderError(f"Unknown AI provider: {name}")


@lru_cache(maxsize=1)
def _prefs() -> Collection:
    return mongo.collection(settings.RUNTIME_SETTINGS_COLLECTION)


def _prefs_store() -> Collection | None:
    try:
        return _prefs()
    except (mongo.NotConfigured, PyMongoError) as exc:
        logger.warning("AI preference store unavailable (%s)", type(exc).__name__)
        return None


def _normalize_chain(primary: str, fallback: str | None) -> list[str]:
    names: list[str] = []
    for name in (primary, fallback):
        if not name:
            continue
        cleaned = name.strip().lower()
        if cleaned not in settings.PROVIDER_NAMES:
            raise PreferenceError(f"unknown:{cleaned}")
        if cleaned not in names:
            names.append(cleaned)
    return names


def _read_admin_chain() -> list[str] | None:
    store = _prefs_store()
    if store is None:
        return None
    try:
        document = store.find_one({"_id": AI_PREF_ID}) or {}
    except PyMongoError as exc:
        logger.warning("AI preference read failed (%s)", type(exc).__name__)
        return None
    primary = str(document.get("primary") or "").strip().lower()
    if not primary:
        return None
    fallback = document.get("fallback")
    fallback_s = str(fallback).strip().lower() if fallback else None
    # Drop removed/unknown names (e.g. legacy ollama) instead of discarding the chain.
    names: list[str] = []
    for name in (primary, fallback_s):
        if not name:
            continue
        if name not in settings.PROVIDER_NAMES:
            logger.warning("Ignoring stored AI provider %r", name)
            continue
        if name not in names:
            names.append(name)
    return names or None


def runtime_chain_names() -> list[str]:
    """Admin override when present, otherwise env chain."""
    admin = _read_admin_chain()
    if admin:
        return admin
    return settings.provider_chain_names()


def active_provider() -> Provider:
    """Build the primary provider from the runtime failover chain."""
    names = runtime_chain_names()
    return build_provider(names[0] if names else settings.GEMINI)


def provider_chain() -> list[Provider]:
    """Configured providers in failover order (configured ones only)."""
    providers: list[Provider] = []
    for name in runtime_chain_names():
        provider = build_provider(name)
        if not provider.configured:
            logger.warning("Skipping AI provider %s — not configured", name)
            continue
        providers.append(provider)
    return providers


def admin_ai_settings() -> dict[str, Any]:
    """Status payload for the admin AI switcher. Never includes credentials."""
    admin_chain = _read_admin_chain()
    chain_names = admin_chain or settings.provider_chain_names()
    primary = chain_names[0] if chain_names else settings.GEMINI
    fallback = chain_names[1] if len(chain_names) > 1 else None
    options: list[dict[str, Any]] = []
    for name in settings.PROVIDER_NAMES:
        provider = build_provider(name)
        options.append(
            {
                "name": name,
                "label": PROVIDER_LABELS.get(name, name),
                "model": provider.model,
                "configured": provider.configured,
                "available": bool(
                    settings.ai_enabled() and provider.configured and is_available(provider)
                ),
            }
        )
    return {
        "enabled": settings.ai_enabled(),
        "primary": primary,
        "fallback": fallback,
        "chain": chain_names,
        "source": "admin" if admin_chain else "env",
        "options": options,
    }


def set_admin_ai_settings(primary: str, fallback: str | None = None) -> dict[str, Any]:
    """Persist primary/fallback providers for admin-controlled failover."""
    chain = _normalize_chain(primary, fallback)
    primary_name = chain[0]
    fallback_name = chain[1] if len(chain) > 1 else None

    primary_provider = build_provider(primary_name)
    if not primary_provider.configured:
        raise PreferenceError(f"not_configured:{primary_name}")
    if fallback_name:
        fallback_provider = build_provider(fallback_name)
        if not fallback_provider.configured:
            raise PreferenceError(f"not_configured:{fallback_name}")

    store = _prefs_store()
    if store is None:
        raise PreferenceError("store_unavailable")

    try:
        store.replace_one(
            {"_id": AI_PREF_ID},
            {
                "_id": AI_PREF_ID,
                "primary": primary_name,
                "fallback": fallback_name,
                "updated_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
    except PyMongoError as exc:
        raise PreferenceError("store_unavailable") from exc

    clear_availability_cache()
    return admin_ai_settings()


def is_available(provider: Provider) -> bool:
    """Cached reachability check for the given provider."""
    ttl = settings.health_cache_seconds()
    now = time.monotonic()
    cached = _availability_cache.get(provider.name)
    if cached and now - cached[0] < ttl:
        return cached[1]
    result = provider.available()
    _availability_cache[provider.name] = (now, result)
    return result


def record_outcome(provider: Provider, succeeded: bool) -> None:
    """Let a real generation result override the cheap reachability probe.

    The probe only asks whether the endpoint answers, which is not the same as
    being able to generate: a model can publish metadata while refusing
    generateContent, or be rejecting calls under load. Recording the outcome
    keeps /api/health honest until the next probe.
    """
    _availability_cache[provider.name] = (time.monotonic(), succeeded)


def generate_json_with_failover(
    prompt: str,
    *,
    timeout: float | None = None,
    max_output_tokens: int,
) -> tuple[Provider, dict]:
    """Try each configured provider until one returns usable JSON.

    Returns the winning provider and payload. Raises ``ProviderError`` only when
    every candidate fails or none are configured.
    """
    chain = provider_chain()
    if not chain:
        raise ProviderError("No AI providers are configured")

    errors: list[str] = []
    for provider in chain:
        ask_timeout = timeout if timeout is not None else provider.ask_timeout
        try:
            payload = provider.generate_json(
                prompt,
                timeout=ask_timeout,
                max_output_tokens=max_output_tokens,
            )
        except ProviderError as exc:
            record_outcome(provider, False)
            logger.warning("AI provider %s failed; trying next: %s", provider.name, exc)
            errors.append(f"{provider.name}: {exc}")
            continue
        record_outcome(provider, True)
        if provider is not chain[0]:
            logger.info("AI failover succeeded with %s", provider.name)
        return provider, payload

    raise ProviderError("; ".join(errors) or "All AI providers failed")


def provider_status() -> dict[str, Any]:
    """The AI fields reported by ``/api/health``. Never includes credentials."""
    enabled = settings.ai_enabled()
    chain = provider_chain()
    primary = chain[0] if chain else active_provider()
    available = False
    if enabled and chain:
        available = any(is_available(provider) for provider in chain)
    admin = _read_admin_chain()
    return {
        "ai_enabled": enabled,
        "ai_available": available,
        "ai_provider": primary.name,
        "ai_model": primary.model,
        "ai_source": "admin" if admin else "env",
        "ai_providers": [
            {
                "name": provider.name,
                "model": provider.model,
                "configured": provider.configured,
                "available": bool(enabled and is_available(provider)),
            }
            for provider in chain
        ],
    }
