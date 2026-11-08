"""Interchangeable JSON-producing model backends: local Ollama or Google Gemini.

Both providers return a parsed JSON object for a prompt, or raise
:class:`ProviderError`. Callers are expected to validate the shape and fall back
to snapshot-derived output, so an unconfigured or unreachable provider degrades
instead of failing the request.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib import request

from ..core import settings

logger = logging.getLogger(__name__)

_JSON_HEADERS = {"Content-Type": "application/json"}

# Reachability is cached so a page that polls /api/health does not probe per call.
_availability_cache: dict[str, tuple[float, bool]] = {}


class ProviderError(RuntimeError):
    """A provider is unconfigured, unreachable, or returned unusable output."""


def clear_availability_cache() -> None:
    """Drop cached reachability results. Used by tests and after config changes."""
    _availability_cache.clear()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict:
    body = json.dumps(payload).encode()
    req = request.Request(url, data=body, headers={**_JSON_HEADERS, **headers}, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


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

    def __init__(self, config: settings.OllamaSettings | settings.GeminiSettings) -> None:
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


class OllamaProvider(Provider):
    """Local Ollama daemon speaking the /api/generate protocol."""

    config: settings.OllamaSettings

    def available(self) -> bool:
        return _reachable(f"{self.config.url}/api/tags", {}, self.config.health_timeout)

    def generate_json(self, prompt: str, *, timeout: float, max_output_tokens: int) -> dict:
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0, "num_predict": max_output_tokens},
        }
        try:
            body = _post_json(f"{self.config.url}/api/generate", payload, {}, timeout)
        except (OSError, ValueError) as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        text = body.get("response") or body.get("thinking") or ""
        try:
            return _json_object(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama returned output that is not JSON") from exc


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
        except (OSError, ValueError) as exc:
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


def active_provider() -> Provider:
    """Build the provider named by ``AI_PROVIDER``."""
    if settings.provider_name() == settings.GEMINI:
        return GeminiProvider(settings.gemini_settings())
    return OllamaProvider(settings.ollama_settings())


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


def provider_status() -> dict[str, Any]:
    """The AI fields reported by ``/api/health``. Never includes credentials."""
    provider = active_provider()
    enabled = settings.ai_enabled()
    return {
        "ai_enabled": enabled,
        "ai_available": bool(enabled and provider.configured and is_available(provider)),
        "ai_provider": provider.name,
        "ai_model": provider.model,
    }
