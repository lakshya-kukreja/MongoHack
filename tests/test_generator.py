"""Offline unit tests for Gemini/OpenAI LLM generation request handling."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.generator import (
    DEFAULT_GEMINI_LLM_MODEL,
    DEFAULT_OPENAI_LLM_MODEL,
    GeminiLLMProvider,
    GeneratorConfigurationError,
    GeneratorProviderError,
    GeneratorRateLimitError,
    GeneratorTimeoutError,
    OpenAILLMProvider,
    create_llm_provider,
)


def _mock_client(handler) -> httpx.Client:
    """Create an httpx client backed by an offline mock transport."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_provider_uses_documented_generate_content_payload() -> None:
    """Gemini sends system instructions separately from the user turn."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key_header"] = request.headers["x-goog-api-key"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Checkout latency followed the deploy [DEPLOY-101]."}],
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    provider = GeminiLLMProvider(
        api_key="gemini-test-key",
        client=_mock_client(handler),
    )

    answer = provider.generate("SYSTEM RULES", "QUESTION")

    assert answer == "Checkout latency followed the deploy [DEPLOY-101]."
    assert provider.model == DEFAULT_GEMINI_LLM_MODEL == "gemini-3.8-flash"
    assert captured["url"].endswith(
        f"/models/{DEFAULT_GEMINI_LLM_MODEL}:generateContent"
    )
    assert captured["api_key_header"] == "gemini-test-key"
    assert captured["payload"] == {
        "systemInstruction": {"parts": [{"text": "SYSTEM RULES"}]},
        "contents": [{"role": "user", "parts": [{"text": "QUESTION"}]}],
    }


def test_gemini_provider_concatenates_visible_parts_and_skips_thoughts() -> None:
    """Thinking-model responses may contain thought parts that must not leak."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "internal reasoning", "thought": True},
                                {"text": "First fact [ALERT-201]."},
                                {"text": "Second fact [SLACK-301]."},
                            ]
                        }
                    }
                ]
            },
        )

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    assert provider.generate("system", "user") == (
        "First fact [ALERT-201].\nSecond fact [SLACK-301]."
    )


def test_gemini_provider_surfaces_prompt_safety_blocks() -> None:
    """A blocked prompt raises a provider error instead of returning empty text."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []},
        )

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorProviderError, match="blocked the prompt: SAFETY"):
        provider.generate("system", "user")


def test_gemini_provider_rejects_missing_candidates() -> None:
    """Malformed Gemini responses are rejected explicitly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorProviderError, match="missing candidates"):
        provider.generate("system", "user")


def test_gemini_provider_maps_timeout() -> None:
    """Transport timeouts map to the dedicated generator timeout error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorTimeoutError, match="timed out"):
        provider.generate("system", "user")


def test_gemini_provider_maps_rate_limit() -> None:
    """HTTP 429 maps to the dedicated rate-limit error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorRateLimitError, match="rate-limited"):
        provider.generate("system", "user")


def test_gemini_provider_requires_api_key_before_network_call() -> None:
    """Missing Gemini keys fail fast without making a request."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called without an API key")

    provider = GeminiLLMProvider(api_key="", client=_mock_client(handler))

    with pytest.raises(GeneratorConfigurationError, match="LLM_API_KEY"):
        provider.generate("system", "user")


def test_openai_provider_remains_supported() -> None:
    """OpenAI chat-completions requests still work unchanged."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Grounded answer [ALERT-201]."}}]},
        )

    provider = OpenAILLMProvider(
        api_key="openai-test-key",
        client=_mock_client(handler),
    )

    answer = provider.generate("SYSTEM RULES", "QUESTION")

    assert answer == "Grounded answer [ALERT-201]."
    assert provider.model == DEFAULT_OPENAI_LLM_MODEL == "gpt-4o-mini"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "SYSTEM RULES"},
        {"role": "user", "content": "QUESTION"},
    ]


def test_create_llm_provider_selects_gemini_by_default_and_keeps_openai() -> None:
    """The factory defaults to Gemini while preserving explicit OpenAI config."""
    default_provider = create_llm_provider(
        SimpleNamespace(LLM_PROVIDER="gemini", LLM_API_KEY="key", LLM_MODEL_NAME="")
    )
    openai_provider = create_llm_provider(
        SimpleNamespace(
            LLM_PROVIDER="openai",
            LLM_API_KEY="key",
            LLM_MODEL_NAME="gpt-4o-mini",
        )
    )

    assert isinstance(default_provider, GeminiLLMProvider)
    assert default_provider.model == DEFAULT_GEMINI_LLM_MODEL
    assert isinstance(openai_provider, OpenAILLMProvider)
    assert openai_provider.model == "gpt-4o-mini"


def test_create_llm_provider_uses_configured_gemini_3_8_flash() -> None:
    """The configured stable Gemini 3.8 Flash model reaches the request URL."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Grounded [ALERT-201]."}]}}]},
        )

    provider = create_llm_provider(
        SimpleNamespace(
            LLM_PROVIDER="gemini",
            LLM_API_KEY="key",
            LLM_MODEL_NAME="gemini-3.8-flash",
        ),
        client=_mock_client(handler),
    )

    assert isinstance(provider, GeminiLLMProvider)
    assert provider.model == "gemini-3.8-flash"
    assert provider.generate("system", "user") == "Grounded [ALERT-201]."
    assert captured["url"].endswith("/models/gemini-3.8-flash:generateContent")


def test_gemini_provider_accepts_models_prefix_without_duplication() -> None:
    """A model configured as ``models/...`` still produces one models/ path segment."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    provider = GeminiLLMProvider(
        api_key="key",
        model="models/gemini-3.8-flash",
        client=_mock_client(handler),
    )

    assert provider.generate("system", "user") == "ok"
    assert captured["url"].endswith("/models/gemini-3.8-flash:generateContent")
    assert "/models/models/" not in captured["url"]


def test_create_llm_provider_rejects_unsupported_provider() -> None:
    """Unsupported provider names fail with a clear configuration error."""
    config = SimpleNamespace(LLM_PROVIDER="unknown", LLM_API_KEY="key", LLM_MODEL_NAME="")

    with pytest.raises(GeneratorConfigurationError, match="Unsupported LLM_PROVIDER"):
        create_llm_provider(config)
