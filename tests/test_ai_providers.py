"""Provider selection, request shaping, and the guarantee that answers degrade."""

import json

import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from apps.api.core import settings
from apps.api.services import ai_providers
from apps.api.services.grounded_ai import answer_research_question, explain_alert_record

RECORD = {
    "product_name": "Herceptin",
    "source_org": "FDA",
    "publish_date": "2026-01-02",
    "reason": "Confirmed counterfeit medicine",
}
SUMMARY = {"records": 3, "publication_start": "2020-01-06", "publication_end": "2026-03-12"}


@pytest.fixture(autouse=True)
def clean_ai_env(monkeypatch):
    """Each test starts from an unconfigured environment and an empty probe cache."""
    for name in (
        "AI_PROVIDER",
        "V2_AI_ENABLED",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_THINKING_BUDGET",
        "OLLAMA_MODEL",
        "OLLAMA_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    ai_providers.clear_availability_cache()
    yield
    ai_providers.clear_availability_cache()


def test_default_provider_is_local_ollama():
    provider = ai_providers.active_provider()

    assert isinstance(provider, ai_providers.OllamaProvider)
    assert provider.name == "ollama"
    assert provider.model == settings.DEFAULT_OLLAMA_MODEL


def test_gemini_is_selected_by_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "GEMINI")

    provider = ai_providers.active_provider()

    assert isinstance(provider, ai_providers.GeminiProvider)
    assert provider.name == "gemini"
    assert provider.model == settings.DEFAULT_GEMINI_MODEL


def test_unknown_provider_falls_back_to_ollama(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")

    assert settings.provider_name() == "ollama"


def test_explanation_model_matches_the_configured_model(monkeypatch):
    """The reported model used to be hardcoded and disagreed with the request."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    sent = {}

    def fake_post(url, payload, headers, timeout):
        sent.update(payload)
        return {
            "response": json.dumps({
                "what_happened": "A regulator published a notice.",
                "why_it_matters": "It concerns the named product.",
                "what_to_do_next": "Read the original notice.",
                "limitations": ["Imported record only."],
            })
        }

    monkeypatch.setattr(ai_providers, "_post_json", fake_post)

    result = explain_alert_record(RECORD)

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3:8b" == sent["model"]


def test_gemini_request_is_json_constrained_and_key_stays_in_the_header(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-value")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "answer": "The snapshot holds 3 records.",
                                    "evidence_used": ["Snapshot counts."],
                                    "limitations": ["Historical snapshot."],
                                })
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_providers, "_post_json", fake_post)

    result = answer_research_question("How many regulators are represented?", [RECORD], SUMMARY)

    assert result["enabled"] is True
    assert result["provider"] == "gemini"
    assert result["model"] == settings.DEFAULT_GEMINI_MODEL
    assert captured["url"].endswith(f"/models/{settings.DEFAULT_GEMINI_MODEL}:generateContent")
    assert captured["headers"] == {"x-goog-api-key": "test-key-value"}
    assert "test-key-value" not in captured["url"]
    generation = captured["payload"]["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["thinkingConfig"] == {"thinkingBudget": 0}


def test_negative_thinking_budget_omits_the_field(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-value")
    monkeypatch.setenv("GEMINI_THINKING_BUDGET", "-1")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(payload=payload)
        raise OSError("stop after capturing the payload")

    monkeypatch.setattr(ai_providers, "_post_json", fake_post)

    explain_alert_record(RECORD)

    assert "thinkingConfig" not in captured["payload"]["generationConfig"]


def test_gemini_without_a_key_degrades_instead_of_failing(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")

    explanation = explain_alert_record(RECORD)
    answer = answer_research_question("Which regulators published the most?", [RECORD], SUMMARY)

    assert explanation["provider"] == "deterministic-fallback"
    assert "counterfeit" in explanation["why_it_matters"].lower()
    assert answer["provider"] == "snapshot-fallback"
    assert "FDA" in answer["answer"]


def test_unreachable_provider_degrades(monkeypatch):
    def fake_post(url, payload, headers, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(ai_providers, "_post_json", fake_post)

    assert explain_alert_record(RECORD)["provider"] == "deterministic-fallback"


def test_prose_wrapped_json_is_recovered():
    assert ai_providers._json_object('Sure! {"answer": "ok"} Hope that helps.') == {"answer": "ok"}


def test_health_reports_the_active_provider_without_leaking_the_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-value")
    monkeypatch.setattr(ai_providers, "_reachable", lambda url, headers, timeout: True)

    body = TestClient(app).get("/api/health").json()

    assert body["ai_provider"] == "gemini"
    assert body["ai_model"] == settings.DEFAULT_GEMINI_MODEL
    assert body["ai_available"] is True
    assert "test-key-value" not in json.dumps(body)


def test_health_marks_gemini_unavailable_without_a_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")

    body = TestClient(app).get("/api/health").json()

    assert body["ai_provider"] == "gemini"
    assert body["ai_available"] is False


def test_a_failed_generation_marks_the_provider_unavailable(monkeypatch):
    """A reachable endpoint that refuses to generate must not report as available.

    gemini-2.5-flash did exactly this: it served model metadata while answering
    generateContent with 404 for new keys.
    """
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-value")
    monkeypatch.setattr(ai_providers, "_reachable", lambda url, headers, timeout: True)

    def refuse(url, payload, headers, timeout):
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr(ai_providers, "_post_json", refuse)
    client = TestClient(app)

    assert client.get("/api/health").json()["ai_available"] is True
    assert explain_alert_record(RECORD)["provider"] == "deterministic-fallback"
    assert client.get("/api/health").json()["ai_available"] is False


def test_a_successful_generation_keeps_the_provider_available(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-value")
    monkeypatch.setattr(ai_providers, "_reachable", lambda url, headers, timeout: False)

    def answer(url, payload, headers, timeout):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "what_happened": "A regulator published a notice.",
                                    "why_it_matters": "It concerns the named product.",
                                    "what_to_do_next": "Read the original notice.",
                                    "limitations": ["Imported record only."],
                                })
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_providers, "_post_json", answer)
    client = TestClient(app)

    assert client.get("/api/health").json()["ai_available"] is False
    assert explain_alert_record(RECORD)["provider"] == "gemini"
    assert client.get("/api/health").json()["ai_available"] is True


def test_disabled_ai_skips_providers_entirely(monkeypatch):
    monkeypatch.setenv("V2_AI_ENABLED", "false")

    def fail(*args, **kwargs):
        raise AssertionError("no provider call should be made when AI is disabled")

    monkeypatch.setattr(ai_providers, "_post_json", fail)

    assert explain_alert_record(RECORD)["provider"] == "deterministic"
    assert answer_research_question("Anything?", [RECORD], SUMMARY)["provider"] == "unavailable"
