"""Offline unit tests for the embedding generation service."""

import json
import math
from types import SimpleNamespace

import httpx
import pytest

from app.models.event import EventRecord, SourceType
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingInputError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    GeminiEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
    generate_embedding,
    generate_embeddings_batch,
    generate_event_embedding,
    generate_event_embeddings,
)


class RecordingProvider(EmbeddingProvider):
    """Deterministic provider that records calls and returns simple vectors."""

    def __init__(self, dimension: int = 3):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [
            [float(len(text)), float(index), 1.0][: self.dimension]
            for index, text in enumerate(texts)
        ]


class FailingProvider(EmbeddingProvider):
    """Provider that simulates an upstream failure."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderError("simulated provider failure")


class MalformedProvider(EmbeddingProvider):
    """Provider that returns a malformed vector payload."""

    def __init__(self, payload):
        self.payload = payload

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.payload


def _make_event(
    source_id: str = "SLACK-301",
    embedding_text: str = "[SLACK] [2026-10-30T14:04:10Z] #incidents-prod (alice.dev): Investigating latency",
) -> EventRecord:
    """Build a canonical event record for embedding tests."""
    return EventRecord(
        source_id=source_id,
        incident_id="INC-2026-042",
        timestamp="2026-10-30T14:04:10Z",
        source_type=SourceType.SLACK,
        author_or_actor="alice.dev",
        channel_or_service="#incidents-prod",
        summary="Investigating latency",
        raw_content="Investigating latency",
        embedding_text=embedding_text,
    )


def _mock_client(handler) -> httpx.Client:
    """Create an httpx client backed by an offline mock transport."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_embedding_returns_validated_float_vector() -> None:
    """A single text produces one validated vector through the injected provider."""
    provider = RecordingProvider()

    vector = generate_embedding("checkout latency spike", provider=provider)

    assert provider.calls == [["checkout latency spike"]]
    assert vector == [22.0, 0.0, 1.0]
    assert all(isinstance(value, float) for value in vector)


def test_generate_embeddings_batch_chunks_large_inputs() -> None:
    """Large batches are split into provider-safe chunks while preserving order."""
    provider = RecordingProvider()
    texts = [f"event-{index}" for index in range(130)]

    vectors = generate_embeddings_batch(texts, batch_size=64, provider=provider)

    assert [len(call) for call in provider.calls] == [64, 64, 2]
    assert len(vectors) == 130
    assert all(len(vector) == 3 for vector in vectors)


def test_empty_batch_returns_empty_without_calling_provider() -> None:
    """An empty batch is valid and must not invoke the provider."""
    provider = RecordingProvider()

    assert generate_embeddings_batch([], provider=provider) == []
    assert provider.calls == []


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_or_whitespace_text_is_rejected(text: str) -> None:
    """Empty or whitespace-only input must not produce a fake vector."""
    with pytest.raises(EmbeddingInputError, match="cannot be empty"):
        generate_embedding(text, provider=RecordingProvider())


def test_non_string_batch_input_is_rejected() -> None:
    """Non-string batch entries are rejected before any provider call."""
    with pytest.raises(EmbeddingInputError, match="must be a string"):
        generate_embeddings_batch(["valid", 123], provider=RecordingProvider())


@pytest.mark.parametrize("batch_size", [0, -1, True])
def test_invalid_batch_size_is_rejected(batch_size: int) -> None:
    """Batch size must be a positive integer and not a boolean."""
    with pytest.raises(EmbeddingInputError, match="batch_size"):
        generate_embeddings_batch(["valid"], batch_size=batch_size, provider=RecordingProvider())


def test_provider_failure_is_propagated_without_fake_vectors() -> None:
    """Provider failures must surface instead of returning fabricated vectors."""
    with pytest.raises(EmbeddingProviderError, match="simulated provider failure"):
        generate_embeddings_batch(["evidence"], provider=FailingProvider())


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([[]], "is empty"),
        ([[1.0, 2.0], [3.0]], "dimension"),
        ([["not-a-number"]], "non-numeric"),
        ([[math.nan]], "non-finite"),
    ],
)
def test_malformed_provider_vectors_are_rejected(payload, message: str) -> None:
    """Malformed provider vectors are rejected by top-level validation."""
    provider = MalformedProvider(payload)

    if message == "dimension":
        texts = ["first", "second"]
    else:
        texts = ["first"]

    with pytest.raises(EmbeddingProviderError, match=message):
        generate_embeddings_batch(texts, provider=provider)


def test_provider_vector_count_mismatch_is_rejected() -> None:
    """A provider returning the wrong number of vectors is rejected."""
    provider = MalformedProvider([[1.0, 2.0, 3.0]])

    with pytest.raises(EmbeddingProviderError, match="returned 1 vectors for 2 inputs"):
        generate_embeddings_batch(["first", "second"], provider=provider)


def test_event_embedding_uses_canonical_embedding_text() -> None:
    """Event embeddings are generated from the canonical embedding_text field."""
    event = _make_event()
    provider = RecordingProvider()

    vector = generate_event_embedding(event, provider=provider)

    assert provider.calls == [[event.embedding_text]]
    assert vector == [float(len(event.embedding_text)), 0.0, 1.0]


def test_event_without_embedding_text_is_rejected() -> None:
    """Events missing canonical text cannot be embedded."""
    event = _make_event(embedding_text="")

    with pytest.raises(EmbeddingInputError, match="no canonical embedding_text"):
        generate_event_embedding(event, provider=RecordingProvider())


def test_event_batch_embedding_preserves_event_order() -> None:
    """Event batch embedding sends canonical texts in event order."""
    events = [
        _make_event("SLACK-301", "[SLACK] first canonical text"),
        _make_event("ALERT-201", "[ALERT] second canonical text"),
        _make_event("DEPLOY-101", "[DEPLOYMENT] third canonical text"),
    ]
    provider = RecordingProvider()

    vectors = generate_event_embeddings(events, batch_size=2, provider=provider)

    assert provider.calls == [
        ["[SLACK] first canonical text", "[ALERT] second canonical text"],
        ["[DEPLOYMENT] third canonical text"],
    ]
    assert len(vectors) == 3


def test_openai_provider_sends_batch_and_sorts_by_index() -> None:
    """OpenAI requests use the configured model and validate response ordering."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [4.0, 5.0, 6.0]},
                    {"index": 0, "embedding": [1.0, 2.0, 3.0]},
                ]
            },
        )

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    vectors = provider.embed_texts(["first", "second"])

    assert vectors == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert captured["url"] == "https://api.openai.com/v1/embeddings"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "text-embedding-3-small",
        "input": ["first", "second"],
    }


def test_openai_provider_rejects_count_mismatch() -> None:
    """OpenAI responses with the wrong vector count are rejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}]},
        )

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="returned 1 vectors for 2 inputs"):
        provider.embed_texts(["first", "second"])


def test_openai_provider_rejects_dimension_mismatch() -> None:
    """OpenAI responses with unexpected dimensions are rejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]},
        )

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="dimension 2, expected 3"):
        provider.embed_texts(["first"])


def test_openai_provider_rejects_malformed_json() -> None:
    """Malformed provider JSON is reported as a provider error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="not valid JSON"):
        provider.embed_texts(["first"])


def test_openai_provider_maps_timeout() -> None:
    """Transport timeouts map to a dedicated embedding timeout error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingTimeoutError, match="timed out"):
        provider.embed_texts(["first"])


def test_openai_provider_maps_rate_limit() -> None:
    """HTTP 429 responses map to a dedicated rate-limit error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingRateLimitError, match="rate-limited"):
        provider.embed_texts(["first"])


def test_openai_provider_maps_server_failure() -> None:
    """HTTP 5xx responses map to a provider error without returning vectors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        expected_dimension=3,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="HTTP 503"):
        provider.embed_texts(["first"])


def test_provider_requires_api_key_before_network_call() -> None:
    """Missing API keys fail fast with a configuration error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called without an API key")

    provider = OpenAIEmbeddingProvider(api_key="", client=_mock_client(handler))

    with pytest.raises(EmbeddingConfigurationError, match="EMBEDDING_API_KEY"):
        provider.embed_texts(["first"])


def _vector(seed: float, dimension: int = 1536) -> list[float]:
    """Build a deterministic finite vector for offline provider tests."""
    return [seed + (index / dimension) for index in range(dimension)]


def test_gemini_provider_requests_1536_dimensions_and_parses_response() -> None:
    """Gemini requests use batchEmbedContents, request 1536 dims, and validate vectors."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key_header"] = request.headers["x-goog-api-key"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": _vector(1.0)},
                    {"values": _vector(2.0)},
                ]
            },
        )

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        client=_mock_client(handler),
    )

    vectors = provider.embed_texts(["first", "second"])

    assert provider.model == "gemini-embedding-2"
    assert provider.expected_dimension == 1536
    assert len(vectors) == 2
    assert vectors[0] == _vector(1.0)
    assert captured["url"].endswith(
        "/models/gemini-embedding-2:batchEmbedContents"
    )
    assert captured["api_key_header"] == "gemini-test-key"
    assert captured["payload"]["requests"] == [
        {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": "first"}]},
            "outputDimensionality": 1536,
        },
        {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": "second"}]},
            "outputDimensionality": 1536,
        },
    ]


def test_gemini_provider_honors_configured_dimension() -> None:
    """A settings-supplied dimension is sent and validated exactly."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"values": _vector(0.5, 1536)}]})

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        output_dimensions=1536,
        client=_mock_client(handler),
    )

    provider.embed_texts(["first"])

    request = captured["payload"]["requests"][0]
    assert request["outputDimensionality"] == 1536
    assert "embedContentConfig" not in request


def test_gemini_batch_payload_uses_top_level_output_dimensionality() -> None:
    """Regression: batchEmbedContents ignores the nested embedContentConfig.

    A live backfill requested 1536 dims through ``embedContentConfig`` but got
    the model's native 3072-dim output, so the dimension flag must be sent as
    the per-request ``EmbedContentRequest.outputDimensionality`` field.
    """
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"values": _vector(1.0)}]})

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        model="gemini-embedding-001",
        client=_mock_client(handler),
    )

    provider.embed_texts(["first"])

    payload = captured["payload"]
    assert payload["requests"][0]["outputDimensionality"] == 1536
    assert "embedContentConfig" not in payload["requests"][0]


def test_gemini_embedding_001_requests_and_validates_1536_dimensions() -> None:
    """gemini-embedding-001 uses the top-level dimension field and 1536-dim contract."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": _vector(1.0)},
                    {"values": _vector(2.0)},
                ]
            },
        )

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        model="gemini-embedding-001",
        client=_mock_client(handler),
    )

    vectors = provider.embed_texts(["first", "second"])

    assert provider.model == "gemini-embedding-001"
    assert provider.expected_dimension == 1536
    assert provider.request_dimensions == 1536
    assert captured["url"].endswith(
        "/models/gemini-embedding-001:batchEmbedContents"
    )
    assert captured["payload"]["requests"] == [
        {
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": "first"}]},
            "outputDimensionality": 1536,
        },
        {
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": "second"}]},
            "outputDimensionality": 1536,
        },
    ]
    assert len(vectors) == 2
    assert all(len(vector) == 1536 for vector in vectors)
    # gemini-embedding-001 does not auto-normalize truncated dimensions, so the
    # client normalizes them to match Google's documented usage.
    for vector in vectors:
        assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)


def test_gemini_embedding_001_rejects_non_1536_response() -> None:
    """gemini-embedding-001 responses must be exactly 1536 dimensions."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": _vector(1.0, 3072)}]})

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        model="gemini-embedding-001",
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="dimension 3072, expected 1536"):
        provider.embed_texts(["first"])


def test_create_embedding_provider_configures_gemini_embedding_001() -> None:
    """Factory config requests and validates 1536 dims for gemini-embedding-001."""
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_API_KEY="key",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSIONS=1536,
    )

    provider = create_embedding_provider(config)

    assert isinstance(provider, GeminiEmbeddingProvider)
    assert provider.model == "gemini-embedding-001"
    assert provider.expected_dimension == 1536
    assert provider.request_dimensions == 1536


def test_gemini_provider_rejects_wrong_returned_dimension() -> None:
    """Gemini responses with the wrong dimension are rejected before storage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 2.0]}]})

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        expected_dimension=1536,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="dimension 2, expected 1536"):
        provider.embed_texts(["first"])


@pytest.mark.parametrize("dimension", [0, 127, 3073, True])
def test_gemini_provider_rejects_unsupported_output_dimensions(dimension) -> None:
    """Gemini output dimensions outside the documented range fail fast."""
    with pytest.raises(EmbeddingConfigurationError, match="between 128 and 3072"):
        GeminiEmbeddingProvider(
            api_key="gemini-test-key",
            output_dimensions=dimension,
        )


def test_gemini_provider_rejects_malformed_embeddings() -> None:
    """Gemini responses missing the values field are rejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"embedding": [1.0]}]})

    provider = GeminiEmbeddingProvider(
        api_key="gemini-test-key",
        expected_dimension=1536,
        client=_mock_client(handler),
    )

    with pytest.raises(EmbeddingProviderError, match="missing the 'values' field"):
        provider.embed_texts(["first"])


def test_create_embedding_provider_uses_existing_settings_names() -> None:
    """Provider factory selects OpenAI or Gemini using existing config fields."""
    openai_config = SimpleNamespace(
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_API_KEY="key",
        EMBEDDING_MODEL_NAME="text-embedding-3-small",
    )
    gemini_config = SimpleNamespace(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_API_KEY="key",
        EMBEDDING_MODEL_NAME="gemini-embedding-2",
        EMBEDDING_DIMENSIONS=1536,
    )

    openai_provider = create_embedding_provider(openai_config)
    gemini_provider = create_embedding_provider(gemini_config)

    assert isinstance(openai_provider, OpenAIEmbeddingProvider)
    assert isinstance(gemini_provider, GeminiEmbeddingProvider)
    assert gemini_provider.expected_dimension == 1536
    assert gemini_provider.request_dimensions == 1536


def test_create_embedding_provider_rejects_unsupported_provider() -> None:
    """Unsupported provider names fail with a clear configuration error."""
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="unknown",
        EMBEDDING_API_KEY="key",
        EMBEDDING_MODEL_NAME="model",
    )

    with pytest.raises(EmbeddingConfigurationError, match="Unsupported EMBEDDING_PROVIDER"):
        create_embedding_provider(config)
