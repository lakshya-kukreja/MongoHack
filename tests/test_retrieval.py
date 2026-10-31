"""Offline tests for the Atlas ``$vectorSearch`` retrieval service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from app.core.config import settings
from app.models.event import EventRecord, SourceType
from app.services.embeddings import EmbeddingProvider
from app.services.retrieval import (
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalService,
    VectorIndexNotFoundError,
)


class StubEmbeddingProvider(EmbeddingProvider):
    """Deterministic offline provider that records the queried texts."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.01] * self.dimension for _ in texts]


class FakeCollection:
    """Minimal collection double that records pipelines and returns fixtures."""

    def __init__(
        self,
        docs: Optional[list[dict[str, Any]]] = None,
        indexes: Optional[list[dict[str, Any]]] = None,
        error: Optional[Exception] = None,
    ):
        self.docs = docs or []
        self.indexes = indexes
        self.error = error
        self.pipelines: list[list[dict[str, Any]]] = []

    def aggregate(self, pipeline: list[dict[str, Any]]):
        self.pipelines.append(pipeline)
        if self.error is not None:
            raise self.error
        return iter(self.docs)

    def list_search_indexes(self):
        if self.indexes is None:
            raise RuntimeError("index listing not supported by this double")
        return list(self.indexes)


class FakeDatabase:
    """Minimal database double keyed by collection name."""

    def __init__(self, collection: FakeCollection):
        self.collection = collection
        self.requested: list[str] = []

    def __getitem__(self, name: str) -> FakeCollection:
        self.requested.append(name)
        assert name == "incident_events"
        return self.collection


def _document(source_id: str = "SLACK-301") -> dict[str, Any]:
    """Build a projected document as Atlas would return it."""
    return {
        "source_id": source_id,
        "incident_id": "INC-2026-042",
        "timestamp": datetime(2026, 10, 30, 14, 12, 0, tzinfo=timezone.utc),
        "source_type": "slack",
        "author_or_actor": "marcus.eng",
        "channel_or_service": "#incidents",
        "summary": "Checkout latency climbing",
        "raw_content": "Latency is climbing after the deploy.",
        "structured_payload": {"channel": "#incidents"},
        "tags": ["latency"],
        "embedding_text": "[SLACK] latency climbing",
        "score": 0.91,
    }


def _service(collection: FakeCollection, **kwargs: Any) -> RetrievalService:
    return RetrievalService(
        database=FakeDatabase(collection),
        embedding_provider=StubEmbeddingProvider(),
        **kwargs,
    )


def test_pipeline_uses_configured_index_vector_field_and_filters() -> None:
    """The pipeline must target the deployment's configured index name."""
    collection = FakeCollection(docs=[])
    service = _service(collection, index_name="vector-index")

    service.search(
        "INC-2026-042",
        "why was checkout slow?",
        limit=3,
        start_time="2026-10-30T13:00:00Z",
        end_time="2026-10-30T15:00:00Z",
        source_types=["slack", "monitoring_alert"],
    )

    stage = collection.pipelines[0][0]["$vectorSearch"]
    assert stage["index"] == "vector-index"
    assert stage["path"] == "embedding"
    assert stage["limit"] == 3
    assert stage["numCandidates"] == RetrievalService.DEFAULT_NUM_CANDIDATES
    assert len(stage["queryVector"]) == 1536
    assert stage["filter"]["incident_id"] == {"$eq": "INC-2026-042"}
    assert stage["filter"]["source_type"] == {"$in": ["slack", "monitoring_alert"]}
    assert set(stage["filter"]["timestamp"]) == {"$gte", "$lte"}

    projection = collection.pipelines[0][1]["$project"]
    assert projection["_id"] == 0
    assert projection["score"] == {"$meta": "vectorSearchScore"}
    assert projection["source_id"] == 1
    assert projection["embedding_text"] == 1


def test_query_embedding_is_generated_from_the_question() -> None:
    """Retrieval embeds exactly the user's question."""
    collection = FakeCollection(docs=[])
    provider = StubEmbeddingProvider()
    service = RetrievalService(
        database=FakeDatabase(collection),
        index_name="vector_index",
        embedding_provider=provider,
    )

    service.search("INC-2026-042", "what changed in v2.4.1?")

    assert provider.calls == [["what changed in v2.4.1?"]]


def test_search_events_maps_projected_documents_to_event_records() -> None:
    """Projected Atlas documents validate into canonical EventRecords."""
    collection = FakeCollection(docs=[_document("SLACK-301")])
    service = _service(collection, index_name="vector_index")

    events = service.search_events("INC-2026-042", "latency")

    assert len(events) == 1
    assert isinstance(events[0], EventRecord)
    assert events[0].source_id == "SLACK-301"
    assert events[0].source_type is SourceType.SLACK
    assert events[0].timestamp == datetime(2026, 10, 30, 14, 12, 0, tzinfo=timezone.utc)


def test_search_with_scores_returns_event_and_score() -> None:
    """Scores are surfaced separately and never leak into EventRecord."""
    collection = FakeCollection(docs=[_document("ALERT-201")])
    service = _service(collection, index_name="vector_index")

    results = service.search_with_scores("INC-2026-042", "latency")

    assert len(results) == 1
    event, score = results[0]
    assert event.source_id == "ALERT-201"
    assert score == pytest.approx(0.91)


def test_missing_index_with_empty_results_raises_instead_of_silently_empty() -> None:
    """Regression: Atlas returns [] for an unknown index name, not an error.

    The live deployment created ``vector-index`` while the code defaulted to
    ``vector_index``. ``$vectorSearch`` returned zero documents, which surfaced
    as a misleading insufficient-evidence answer. A missing index must fail
    loudly.
    """
    collection = FakeCollection(
        docs=[],
        indexes=[{"name": "vector-index", "status": "READY", "queryable": True}],
    )
    service = _service(collection, index_name="vector_index")

    with pytest.raises(VectorIndexNotFoundError, match="vector-index"):
        service.search("INC-2026-042", "latency")


def test_matching_index_with_no_matches_returns_empty() -> None:
    """A correctly named, ready index may legitimately return no documents."""
    collection = FakeCollection(
        docs=[],
        indexes=[{"name": "vector_index", "status": "READY", "queryable": True}],
    )
    service = _service(collection, index_name="vector_index")

    assert service.search("INC-2026-042", "latency") == []


def test_not_ready_index_raises() -> None:
    """A non-queryable index is a configuration failure, not missing evidence."""
    collection = FakeCollection(
        docs=[],
        indexes=[{"name": "vector_index", "status": "BUILDING", "queryable": False}],
    )
    service = _service(collection, index_name="vector_index")

    with pytest.raises(VectorIndexNotFoundError, match="not ready"):
        service.search("INC-2026-042", "latency")


def test_index_metadata_unavailable_does_not_mask_legitimate_empty_results() -> None:
    """Doubles (and restricted credentials) without index metadata stay permissive."""
    collection = FakeCollection(docs=[])
    service = _service(collection, index_name="vector_index")

    assert service.search("INC-2026-042", "latency") == []


def test_default_index_name_comes_from_settings() -> None:
    """Operators can point retrieval at the deployed Atlas index name."""
    collection = FakeCollection(docs=[])
    service = RetrievalService(
        database=FakeDatabase(collection),
        embedding_provider=StubEmbeddingProvider(),
    )

    assert service.index_name == settings.VECTOR_INDEX_NAME


@pytest.mark.parametrize(
    ("incident_id", "query", "message"),
    [
        ("", "latency", "incident_id"),
        ("INC-2026-042", "", "query"),
    ],
)
def test_blank_inputs_are_rejected(
    incident_id: str, query: str, message: str
) -> None:
    """Invalid input fails before any embedding or database call."""
    collection = FakeCollection(docs=[])
    service = _service(collection, index_name="vector_index")

    with pytest.raises(RetrievalConfigurationError, match=message):
        service.search(incident_id, query)

    assert collection.pipelines == []


def test_dimension_error_is_mapped_to_retrieval_error() -> None:
    """Atlas dimension errors surface as RetrievalError, not a raw driver error."""
    collection = FakeCollection(
        docs=[],
        error=RuntimeError("queryVector has invalid dimension 3072, expected 1536"),
    )
    service = _service(collection, index_name="vector_index")

    with pytest.raises(RetrievalError, match="dimension mismatch"):
        service.search("INC-2026-042", "latency")
