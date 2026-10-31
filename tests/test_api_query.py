"""Tests for the incident query (RAG) endpoint."""
from fastapi.testclient import TestClient
from app.models.event import EventRecord, SourceType
from app.services.storage import StorageService
from app.services.generator import MockLLMProvider, get_generator, Generator
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
