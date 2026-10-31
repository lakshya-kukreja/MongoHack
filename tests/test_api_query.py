"""Tests for the incident query (RAG) endpoint."""
from fastapi.testclient import TestClient
from app.models.event import EventRecord, SourceType
from app.services.storage import StorageService
from app.services.generator import (
    GeneratorConfigurationError,
    GeneratorProviderError,
    GeneratorRateLimitError,
    GeneratorTimeoutError,
    MockLLMProvider,
    get_generator,
    Generator,
)
from app.services.retrieval import RetrievalService
from app.services.embeddings import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.calls = []
    
    def embed_texts(self, texts):
        self.calls.append(list(texts))
        # Return simple deterministic vectors
        vectors = []
        for i, text in enumerate(texts):
            vec = [0.1] * self.dimension
            vec[0] = float(len(text))
            vec[1] = float(i)
            vectors.append(vec)
        return vectors


class MockRetrievalService(RetrievalService):
    def __init__(self, events_to_return=None):
        self.events_to_return = events_to_return or []
        self.search_calls = []
    
    def search_events(self, incident_id, query, limit=10, start_time=None, end_time=None, source_types=None):
        self.search_calls.append((incident_id, query, limit))
        return self.events_to_return[:limit]


def test_query_endpoint_success_with_citations(client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService):
    """Test successful query with citations."""
    reset_storage.insert_events(sample_demo_events)
    
    # Create mock retrieval service returning relevant events
    relevant = [e for e in sample_demo_events if e.source_id in ["ALERT-201", "SLACK-301"]]
    mock_retrieval = MockRetrievalService(events_to_return=relevant)
    mock_llm = MockLLMProvider(
        response="The first sign of trouble was at 14:02:00Z when Datadog issued a CRITICAL alert showing P99 latency exceeded 2000ms [ALERT-201]. Alice first noticed it in #incidents-prod at 14:04:10Z [SLACK-301]."
    )
    mock_generator = Generator(retrieval_service=mock_retrieval, llm_provider=mock_llm)
    
    app = client.app
    from app.services.generator import get_generator
    app.dependency_overrides[get_generator] = lambda: mock_generator
    
    resp = client.post(
        "/api/incidents/INC-2026-042/query",
        json={"query": "What was the first sign of trouble and who noticed it?"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "citations" in data
    assert "unverified_citations" in data
    assert "retrieved_events" in data
    assert len(data["citations"]) == 2
    assert any(c["source_id"] == "ALERT-201" for c in data["citations"])
    assert data["unverified_citations"] == []
    
    app.dependency_overrides.pop(get_generator, None)


def test_query_endpoint_insufficient_evidence(client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService):
    """Test query with insufficient evidence."""
    reset_storage.insert_events(sample_demo_events)
    
    mock_retrieval = MockRetrievalService(events_to_return=[])
    mock_llm = MockLLMProvider()
    mock_generator = Generator(retrieval_service=mock_retrieval, llm_provider=mock_llm)
    
    app = client.app
    from app.services.generator import get_generator
    app.dependency_overrides[get_generator] = lambda: mock_generator
    
    resp = client.post(
        "/api/incidents/INC-2026-042/query",
        json={"query": "Did an expired SSL certificate cause this outage?"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "insufficient evidence" in data["answer"].lower()
    assert data["citations"] == []
    assert data["unverified_citations"] == []
    
    app.dependency_overrides.pop(get_generator, None)


def test_query_endpoint_hallucinated_citations_rejected(client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService):
    """Test that hallucinated citations are rejected."""
    reset_storage.insert_events(sample_demo_events)
    
    relevant = [e for e in sample_demo_events if e.source_id == "ALERT-201"]
    mock_retrieval = MockRetrievalService(events_to_return=relevant)
    mock_llm = MockLLMProvider(
        response="Something happened [ALERT-201] and also [FAKE-999] which is not real."
    )
    mock_generator = Generator(retrieval_service=mock_retrieval, llm_provider=mock_llm)
    
    app = client.app
    from app.services.generator import get_generator
    app.dependency_overrides[get_generator] = lambda: mock_generator
    
    resp = client.post(
        "/api/incidents/INC-2026-042/query",
        json={"query": "What happened?"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["citations"]) == 1
    assert data["citations"][0]["source_id"] == "ALERT-201"
    assert "FAKE-999" in data["unverified_citations"]
    
    app.dependency_overrides.pop(get_generator, None)


def test_query_endpoint_incident_not_found(client: TestClient):
    """Test query for non-existent incident returns 404."""
    resp = client.post(
        "/api/incidents/NONEXISTENT/query",
        json={"query": "What happened?"}
    )
    assert resp.status_code == 404


def test_query_endpoint_invalid_request(client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService):
    """Test query with missing query returns validation error."""
    reset_storage.insert_events(sample_demo_events)
    resp = client.post(
        "/api/incidents/INC-2026-042/query",
        json={}
    )
    assert resp.status_code == 422


class _RaisingGenerator:
    """Generator double that raises a pre-built exception from the pipeline."""

    def __init__(self, exc: Exception):
        self.exc = exc

    def query(self, **kwargs):
        raise self.exc


def _override_generator(client: TestClient, exc: Exception) -> None:
    client.app.dependency_overrides[get_generator] = lambda: _RaisingGenerator(exc)


def test_query_endpoint_maps_provider_auth_error_to_generic_503(
    client: TestClient,
    sample_demo_events: list[EventRecord],
    reset_storage: StorageService,
    caplog,
):
    """A 401/403 must stay a generic 503 to the client while logs show details."""
    reset_storage.insert_events(sample_demo_events)
    exc = GeneratorProviderError(
        "gemini request failed (HTTP 401, category=authentication_failed): API key not valid",
        provider="gemini",
        model="gemini-3.8-flash",
        status_code=401,
        error_category="authentication_failed",
        provider_status="UNAUTHENTICATED",
    )
    _override_generator(client, exc)

    with caplog.at_level("WARNING", logger="incident_investigator"):
        resp = client.post(
            "/api/incidents/INC-2026-042/query",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 503
    assert resp.json() == {"detail": "LLM provider unavailable or rate-limited"}

    log_text = caplog.text
    assert "authentication_failed" in log_text
    assert "401" in log_text
    assert "gemini-3.8-flash" in log_text
    assert "UNAUTHENTICATED" in log_text


def test_query_endpoint_maps_rate_limit_to_503_and_logs_category(
    client: TestClient,
    sample_demo_events: list[EventRecord],
    reset_storage: StorageService,
    caplog,
):
    """Quota exhaustion is logged as rate_limited, client detail stays generic."""
    reset_storage.insert_events(sample_demo_events)
    exc = GeneratorRateLimitError(
        "gemini request failed (HTTP 429, category=rate_limited): quota exceeded",
        provider="gemini",
        model="gemini-3.8-flash",
        status_code=429,
        error_category="rate_limited",
        provider_status="RESOURCE_EXHAUSTED",
    )
    _override_generator(client, exc)

    with caplog.at_level("WARNING", logger="incident_investigator"):
        resp = client.post(
            "/api/incidents/INC-2026-042/query",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 503
    assert resp.json() == {"detail": "LLM provider unavailable or rate-limited"}
    assert "rate_limited" in caplog.text
    assert "429" in caplog.text


def test_query_endpoint_maps_timeout_to_504(
    client: TestClient,
    sample_demo_events: list[EventRecord],
    reset_storage: StorageService,
    caplog,
):
    """Timeouts map to the documented 504 contract."""
    reset_storage.insert_events(sample_demo_events)
    exc = GeneratorTimeoutError(
        "LLM request timed out after 30.0 seconds",
        provider="gemini",
        model="gemini-3.8-flash",
        error_category="timeout",
    )
    _override_generator(client, exc)

    with caplog.at_level("WARNING", logger="incident_investigator"):
        resp = client.post(
            "/api/incidents/INC-2026-042/query",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 504
    assert resp.json() == {"detail": "LLM provider timed out"}
    assert "timeout" in caplog.text


def test_query_endpoint_maps_configuration_error_without_misclassification(
    client: TestClient,
    sample_demo_events: list[EventRecord],
    reset_storage: StorageService,
    caplog,
):
    """Configuration failures are logged by their real type, not as provider errors."""
    reset_storage.insert_events(sample_demo_events)
    exc = GeneratorConfigurationError("LLM_API_KEY is required for Gemini")
    _override_generator(client, exc)

    with caplog.at_level("WARNING", logger="incident_investigator"):
        resp = client.post(
            "/api/incidents/INC-2026-042/query",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 503
    assert resp.json() == {"detail": "LLM provider unavailable or rate-limited"}
    assert "GeneratorConfigurationError" in caplog.text


def test_query_endpoint_logs_do_not_leak_api_keys(
    client: TestClient,
    sample_demo_events: list[EventRecord],
    reset_storage: StorageService,
    caplog,
):
    """Even if an exception message contains a key, logs must redact it."""
    reset_storage.insert_events(sample_demo_events)
    leaked_key = "AIzaSyD-very-secret-key-material-1234567890"
    exc = GeneratorProviderError(
        f"gemini request failed (HTTP 401): key {leaked_key} token=super-secret",
        provider="gemini",
        model="gemini-3.8-flash",
        status_code=401,
        error_category="authentication_failed",
    )
    _override_generator(client, exc)

    with caplog.at_level("WARNING", logger="incident_investigator"):
        resp = client.post(
            "/api/incidents/INC-2026-042/query",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 503
    assert leaked_key not in resp.text
    assert leaked_key not in caplog.text
    assert "super-secret" not in caplog.text
    assert "[redacted]" in caplog.text

