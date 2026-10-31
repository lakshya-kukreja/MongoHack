"""Offline unit tests for Gemini/OpenAI LLM generation request handling."""

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.models.event import EventRecord, SourceType
from app.services import generator as generator_module
from app.services.generator import (
    DEFAULT_GEMINI_LLM_MODEL,
    DEFAULT_LLM_REQUEST_DEADLINE_SECONDS,
    DEFAULT_LLM_TIMEOUT,
    DEFAULT_OPENAI_LLM_MODEL,
    GeminiLLMProvider,
    LLMRetryPolicy,
    Generator,
    GeneratorConfigurationError,
    GeneratorError,
    GeneratorProviderError,
    GeneratorRateLimitError,
    GeneratorTimeoutError,
    MockLLMProvider,
    OpenAILLMProvider,
    create_llm_provider,
    describe_exception_for_logging,
    generate_answer,
)


def _mock_client(handler) -> httpx.Client:
    """Create an httpx client backed by an offline mock transport."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def _gemini_ok_body(text: str = "Grounded answer [ALERT-201].") -> dict:
    """Minimal successful Gemini ``generateContent`` response body."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _gemini_503_body() -> dict:
    """Minimal transient-capacity error body matching live Gemini responses."""
    return {
        "error": {
            "code": 503,
            "status": "UNAVAILABLE",
            "message": "The model is experiencing high demand. Please try again later.",
        }
    }


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
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "LOW"}},
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
    """HTTP 429 maps to the dedicated rate-limit error with safe metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}},
        )

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=lambda _delay: None,
    )

    with pytest.raises(GeneratorRateLimitError) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert "rate_limited" in str(exc)
    assert exc.provider == "gemini"
    assert exc.model == DEFAULT_GEMINI_LLM_MODEL
    assert exc.status_code == 429
    assert exc.provider_status == "RESOURCE_EXHAUSTED"
    assert exc.error_category == "rate_limited"
    assert exc.attempts == 3


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


def _sample_event() -> EventRecord:
    """Build one minimal evidence record for generator pipeline tests."""
    return EventRecord(
        source_id="ALERT-201",
        incident_id="INC-2026-042",
        timestamp=datetime(2026, 10, 28, 14, 2, 0, tzinfo=timezone.utc),
        source_type=SourceType.MONITORING_ALERT,
        author_or_actor="Datadog",
        channel_or_service="checkout-api",
        summary="P99 latency exceeded 2000ms",
        raw_content="P99 latency exceeded 2000ms on checkout-api.",
    )


@pytest.mark.parametrize(
    ("status_code", "provider_status", "expected_category"),
    [
        (400, "INVALID_ARGUMENT", "invalid_request"),
        (401, "UNAUTHENTICATED", "authentication_failed"),
        (403, "PERMISSION_DENIED", "permission_denied"),
        (404, "NOT_FOUND", "model_not_found"),
        (429, "RESOURCE_EXHAUSTED", "rate_limited"),
        (500, "INTERNAL", "provider_unavailable"),
        (503, "UNAVAILABLE", "provider_unavailable"),
    ],
)
def test_gemini_provider_maps_http_errors_to_safe_diagnostics(
    status_code: int,
    provider_status: str,
    expected_category: str,
) -> None:
    """Each upstream status maps to a stable, non-secret category."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "code": status_code,
                    "status": provider_status,
                    "message": f"upstream failure for {provider_status}",
                }
            },
        )

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=lambda _delay: None,
    )
    expected_class = (
        GeneratorRateLimitError if status_code == 429 else GeneratorProviderError
    )

    with pytest.raises(expected_class) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert exc.provider == "gemini"
    assert exc.model == DEFAULT_GEMINI_LLM_MODEL
    assert exc.status_code == status_code
    assert exc.provider_status == provider_status
    assert exc.error_category == expected_category
    assert str(status_code) in str(exc)
    assert provider_status in str(exc)
    # Transient statuses spend the full budget; permanent ones never retry.
    assert exc.attempts == (3 if status_code in {429, 500, 503} else 1)


def test_provider_error_message_redacts_api_keys() -> None:
    """Upstream text must never echo API keys or tokens into logs or responses."""
    leaked_key = "AIzaSyD-very-secret-key-material-1234567890"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "status": "UNAUTHENTICATED",
                    "message": f"API key not valid: {leaked_key} token=super-secret",
                }
            },
        )

    provider = GeminiLLMProvider(api_key=leaked_key, client=_mock_client(handler))

    with pytest.raises(GeneratorProviderError) as excinfo:
        provider.generate("system", "user")

    text = str(excinfo.value)
    assert leaked_key not in text
    assert "super-secret" not in text
    assert "[redacted]" in text

    log_fields = describe_exception_for_logging(excinfo.value)
    assert leaked_key not in json.dumps(log_fields)
    assert "super-secret" not in json.dumps(log_fields)


def test_openai_provider_maps_authentication_failure() -> None:
    """OpenAI auth failures expose status/category without changing the class."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"type": "invalid_request_error", "message": "invalid key"}},
        )

    provider = OpenAILLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorProviderError) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert exc.provider == "openai"
    assert exc.status_code == 401
    assert exc.provider_status == "invalid_request_error"
    assert exc.error_category == "authentication_failed"


def test_provider_timeout_carries_diagnostics() -> None:
    """Timeouts keep the dedicated type and safe metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorTimeoutError) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert exc.provider == "gemini"
    assert exc.status_code is None
    assert exc.error_category == "timeout"


def test_generate_answer_preserves_provider_exception_metadata() -> None:
    """The pipeline must not rewrap and hide the upstream status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"status": "PERMISSION_DENIED", "message": "model disabled"}},
        )

    provider = GeminiLLMProvider(api_key="key", client=_mock_client(handler))

    with pytest.raises(GeneratorProviderError) as excinfo:
        generate_answer("What happened?", [_sample_event()], llm_provider=provider)

    exc = excinfo.value
    assert exc.status_code == 403
    assert exc.error_category == "permission_denied"
    assert exc.provider == "gemini"
    # The original, sanitized upstream detail must survive the pipeline.
    assert "model disabled" in str(exc)


def test_generate_answer_preserves_configuration_error_type() -> None:
    """A configuration failure must not be misclassified as a provider error."""

    class UnsupportedProvider:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise GeneratorConfigurationError("LLM_API_KEY is required for Gemini")

    with pytest.raises(GeneratorConfigurationError):
        generate_answer("What happened?", [_sample_event()], llm_provider=UnsupportedProvider())


def test_generate_answer_wraps_unexpected_exception_with_category() -> None:
    """Unknown provider failures are still classified, without leaking details."""

    class ExplodingProvider:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("boom secret=do-not-log")

    with pytest.raises(GeneratorProviderError) as excinfo:
        generate_answer("What happened?", [_sample_event()], llm_provider=ExplodingProvider())

    exc = excinfo.value
    assert exc.error_category == "unexpected_error"
    assert isinstance(exc, GeneratorError)
    # Unexpected exception text is replaced, so embedded secrets never propagate.
    assert "do-not-log" not in str(exc)


@pytest.mark.parametrize(
    ("timeout_exception", "expected_phase"),
    [
        (httpx.ConnectTimeout, "connect"),
        (httpx.ReadTimeout, "read"),
        (httpx.WriteTimeout, "write"),
        (httpx.PoolTimeout, "pool"),
        (httpx.TimeoutException, "unknown"),
    ],
)
def test_timeout_phase_is_classified(timeout_exception, expected_phase: str) -> None:
    """Operators can tell whether connecting or waiting for a response timed out."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise timeout_exception("simulated timeout")

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=lambda _delay: None,
    )

    with pytest.raises(GeneratorTimeoutError) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert exc.timeout_phase == expected_phase
    assert f"phase={expected_phase}" in str(exc)
    assert describe_exception_for_logging(exc)["timeout_phase"] == expected_phase
    # Connect/pool timeouts happen before the model runs, so they are retried.
    # Read/write/unknown timeouts could duplicate work and fail immediately.
    assert exc.attempts == (3 if expected_phase in {"connect", "pool"} else 1)


def test_create_llm_provider_preserves_the_documented_30s_generation_timeout() -> None:
    """The spec's 30-second generation timeout is unchanged by this investigation."""
    provider = create_llm_provider(
        SimpleNamespace(LLM_PROVIDER="gemini", LLM_API_KEY="key", LLM_MODEL_NAME="")
    )

    assert provider.timeout == DEFAULT_LLM_TIMEOUT == 30.0


class _StaticRetrievalService:
    """Minimal retrieval double that returns a fixed result set."""

    def __init__(self, events: list[EventRecord]):
        self.events = events
        self.calls = 0

    def search_events(
        self,
        incident_id,
        query,
        limit=10,
        start_time=None,
        end_time=None,
        source_types=None,
    ):
        self.calls += 1
        return self.events[:limit]


def test_generator_query_invokes_llm_exactly_once() -> None:
    """One backend query performs one retrieval and one generation call (no retries)."""
    retrieval = _StaticRetrievalService([_sample_event()])
    llm = MockLLMProvider(response="Grounded answer [ALERT-201].")
    generator = Generator(retrieval_service=retrieval, llm_provider=llm)

    response = generator.query("INC-2026-042", "What happened?")

    assert retrieval.calls == 1
    assert len(llm.calls) == 1
    assert response.citations[0]["source_id"] == "ALERT-201"


def test_gemini_retries_transient_503_then_succeeds() -> None:
    """A single capacity 503 must not surface when the next attempt works."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            return httpx.Response(503, json=_gemini_503_body())
        return httpx.Response(200, json=_gemini_ok_body())

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=sleeps.append,
        rand=lambda _low, high: high,
    )

    assert provider.generate("system", "user") == "Grounded answer [ALERT-201]."
    assert calls == [1, 2]
    assert len(sleeps) == 1
    # First backoff ceiling is the configured 0.5s base delay.
    assert 0.0 <= sleeps[0] <= 0.5


def test_gemini_repeated_503_exhausts_retry_budget() -> None:
    """Persistent capacity failures stop after max_attempts and keep diagnostics."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        return httpx.Response(503, json=_gemini_503_body())

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=sleeps.append,
        rand=lambda _low, high: high,
    )

    with pytest.raises(GeneratorProviderError) as excinfo:
        provider.generate("system", "user")

    exc = excinfo.value
    assert calls == [1, 2, 3]
    assert exc.attempts == 3
    assert exc.status_code == 503
    assert exc.provider_status == "UNAVAILABLE"
    assert exc.error_category == "provider_unavailable"
    # Two retries, with exponential backoff ceilings of 0.5s then 1.0s.
    assert sleeps == [0.5, 1.0]


def test_gemini_does_not_retry_permanent_403() -> None:
    """A disabled model is permanent; retrying only wastes the request budget."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "status": "PERMISSION_DENIED",
                    "message": "model is disabled for this project",
                }
            },
        )

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=sleeps.append,
    )

    with pytest.raises(GeneratorProviderError) as excinfo:
        provider.generate("system", "user")

    assert calls == [1]
    assert sleeps == []
    assert excinfo.value.attempts == 1
    assert excinfo.value.error_category == "permission_denied"


def test_gemini_does_not_retry_read_timeout() -> None:
    """Read timeouts fail fast: the model may already be generating an answer."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        raise httpx.ReadTimeout("read timed out")

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        sleep=sleeps.append,
    )

    with pytest.raises(GeneratorTimeoutError) as excinfo:
        provider.generate("system", "user")

    assert calls == [1]
    assert sleeps == []
    assert excinfo.value.timeout_phase == "read"
    assert excinfo.value.attempts == 1


def test_retry_policy_enforces_attempt_and_deadline_bounds() -> None:
    """Backoff is exponential, bounded by jitter and by the shared deadline."""
    policy = LLMRetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.5,
        max_delay_seconds=4.0,
        deadline_seconds=30.0,
    )

    assert policy.backoff_delay(1, 30.0, rand=lambda _low, high: high) == 0.5
    assert policy.backoff_delay(2, 30.0, rand=lambda _low, high: high) == 1.0
    assert policy.backoff_delay(3, 30.0, rand=lambda _low, high: high) is None
    # A backoff that would consume the remaining deadline must be refused.
    assert policy.backoff_delay(1, 0.25, rand=lambda _low, _high: 0.5) is None
    assert policy.backoff_delay(1, 0.0, rand=lambda _low, _high: 0.0) is None


def test_default_retry_policy_matches_documented_30s_contract() -> None:
    """The default budget keeps the documented 30s generation contract."""
    policy = LLMRetryPolicy()

    assert policy.max_attempts == 3
    assert policy.base_delay_seconds == 0.5
    assert policy.max_delay_seconds == 4.0
    assert policy.deadline_seconds == DEFAULT_LLM_REQUEST_DEADLINE_SECONDS == 30.0


def test_overall_deadline_stops_further_attempts(monkeypatch) -> None:
    """Retries never extend one request beyond the hard wall-clock deadline."""
    clock = {"now": 0.0}
    monkeypatch.setattr(generator_module.time, "monotonic", lambda: clock["now"])
    timeouts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        clock["now"] += 5.0
        return httpx.Response(503, json=_gemini_503_body())

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        retry_policy=LLMRetryPolicy(
            max_attempts=10,
            base_delay_seconds=4.0,
            max_delay_seconds=4.0,
            deadline_seconds=10.0,
        ),
        sleep=lambda delay: clock.__setitem__("now", clock["now"] + delay),
        rand=lambda _low, high: high,
    )

    with pytest.raises(GeneratorProviderError) as excinfo:
        provider.generate("system", "user")

    # Attempt 1 burns 5s + 4s backoff, leaving 1s. Attempt 2 is clamped to that
    # remaining second, then the 503 deadline exhausts the budget.
    assert len(timeouts) == 2
    assert timeouts[1]["read"] <= 1.0
    assert excinfo.value.attempts == 2


def test_thinking_config_is_sent_only_to_gemini() -> None:
    """Gemini gets ``thinkingLevel``; OpenAI payloads stay byte-compatible."""
    gemini_payloads: list[dict] = []
    openai_payloads: list[dict] = []

    def gemini_handler(request: httpx.Request) -> httpx.Response:
        gemini_payloads.append(json.loads(request.content))
        return httpx.Response(200, json=_gemini_ok_body())

    def openai_handler(request: httpx.Request) -> httpx.Response:
        openai_payloads.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "answer"}}]}
        )

    gemini = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(gemini_handler),
        thinking_level="high",
    )
    openai = OpenAILLMProvider(
        api_key="key",
        client=_mock_client(openai_handler),
    )

    assert gemini.generate("system", "user") == "Grounded answer [ALERT-201]."
    assert openai.generate("system", "user") == "answer"

    assert gemini_payloads[0]["generationConfig"] == {
        "thinkingConfig": {"thinkingLevel": "HIGH"}
    }
    assert "generationConfig" not in openai_payloads[0]
    assert "thinkingConfig" not in json.dumps(openai_payloads[0])


def test_thinking_level_none_omits_generation_config() -> None:
    """An explicit 'none' leaves thinking at the provider default."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_gemini_ok_body())

    provider = GeminiLLMProvider(
        api_key="key",
        client=_mock_client(handler),
        thinking_level="none",
    )

    provider.generate("system", "user")

    assert "generationConfig" not in captured["payload"]


def test_create_llm_provider_defaults_to_low_thinking_level() -> None:
    """Incident extraction defaults to low thinking for predictable latency."""
    provider = create_llm_provider(
        SimpleNamespace(LLM_PROVIDER="gemini", LLM_API_KEY="key", LLM_MODEL_NAME="")
    )

    assert isinstance(provider, GeminiLLMProvider)
    assert provider.thinking_level == "LOW"


def test_create_llm_provider_reads_thinking_and_retry_settings() -> None:
    """Operators can raise thinking or tighten the retry budget via settings."""
    provider = create_llm_provider(
        SimpleNamespace(
            LLM_PROVIDER="gemini",
            LLM_API_KEY="key",
            LLM_MODEL_NAME="",
            LLM_GEMINI_THINKING_LEVEL="high",
            LLM_MAX_ATTEMPTS=4,
            LLM_RETRY_BASE_DELAY_SECONDS=0.25,
            LLM_RETRY_MAX_DELAY_SECONDS=2.0,
            LLM_REQUEST_DEADLINE_SECONDS=12.0,
        )
    )

    assert isinstance(provider, GeminiLLMProvider)
    assert provider.thinking_level == "HIGH"
    assert provider.retry_policy == LLMRetryPolicy(
        max_attempts=4,
        base_delay_seconds=0.25,
        max_delay_seconds=2.0,
        deadline_seconds=12.0,
    )


def test_create_llm_provider_rejects_unsupported_thinking_level() -> None:
    """Typos in the thinking setting fail fast instead of being sent upstream."""
    with pytest.raises(
        GeneratorConfigurationError, match="Unsupported LLM_GEMINI_THINKING_LEVEL"
    ):
        create_llm_provider(
            SimpleNamespace(
                LLM_PROVIDER="gemini",
                LLM_API_KEY="key",
                LLM_MODEL_NAME="",
                LLM_GEMINI_THINKING_LEVEL="turbo",
            )
        )


def test_retry_logging_omits_prompt_and_api_key(caplog) -> None:
    """Retry diagnostics stay useful without leaking credentials or evidence."""
    secret = "AIzaSyD-very-secret-key-material-1234567890"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json=_gemini_503_body())

    provider = GeminiLLMProvider(
        api_key=secret,
        client=_mock_client(handler),
        retry_policy=LLMRetryPolicy(max_attempts=2),
        sleep=lambda _delay: None,
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(GeneratorProviderError):
            provider.generate("SYSTEM SECRET PROMPT", "USER SECRET PROMPT")

    assert "Retrying LLM request" in caplog.text
    assert secret not in caplog.text
    assert "SECRET PROMPT" not in caplog.text


