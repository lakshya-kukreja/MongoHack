"""Offline tests for the idempotent embedding backfill workflow."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.models.event import EventRecord, SourceType
from app.services.embedding_backfill import (
    ATLAS_VECTOR_DIMENSIONS,
    BackfillConfigurationError,
    EmbeddingBackfillError,
    EmbeddingBackfillService,
    classify_embedding,
)
from app.services.embeddings import (
    EmbeddingDimensionError,
    EmbeddingProvider,
)
from app.services.storage import StorageService
from tests.mock_mongo import MockDatabase, MockMongoClient


class FixedDimensionProvider(EmbeddingProvider):
    """Deterministic offline provider returning a fixed-dimension vector."""

    def __init__(self, dimension: int = ATLAS_VECTOR_DIMENSIONS):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [
            [float(index + 1) / self.dimension for _ in range(self.dimension)]
            for index, _ in enumerate(texts)
        ]


@pytest.fixture
def mock_db() -> MockDatabase:
    """Fresh in-memory MongoDB database double."""
    return MockMongoClient()["incident_investigator"]


def _storage(mock_db: MockDatabase) -> StorageService:
    return StorageService(database=mock_db)


def _single_event() -> EventRecord:
    return EventRecord(
        source_id="ALERT-201",
        incident_id="INC-2026-042",
        timestamp="2026-10-30T14:02:00Z",
        source_type=SourceType.MONITORING_ALERT,
        author_or_actor="datadog-monitor",
        channel_or_service="checkout-service",
        summary="Latency breach",
        raw_content="P99 latency exceeded threshold",
        embedding_text="[ALERT] [2026-10-30T14:02:00Z] checkout-service: P99 latency exceeded threshold",
    )


def test_atlas_index_and_backfill_dimension_contract_match() -> None:
    """The backfill default must match the committed Atlas vector index."""
    index_path = Path(__file__).resolve().parents[1] / "backend" / "atlas_vector_index.json"
    index_spec = json.loads(index_path.read_text(encoding="utf-8"))
    vector_field = next(field for field in index_spec["fields"] if field["type"] == "vector")

    assert ATLAS_VECTOR_DIMENSIONS == 1536
    assert vector_field["path"] == "embedding"
    assert vector_field["numDimensions"] == ATLAS_VECTOR_DIMENSIONS


def test_audit_reports_missing_null_and_empty_embeddings(
    mock_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """The read-only audit reports the real no-vector state without writes."""
    storage = _storage(mock_db)
    storage.insert_events(sample_demo_events)

    service = EmbeddingBackfillService(storage=storage, provider=FixedDimensionProvider())
    audit = service.audit(incident_id="INC-2026-042")

    assert audit.scanned == 17
    assert audit.missing == 17
    assert audit.invalid == 0
    assert audit.valid == 0
    assert all(doc["embedding"] is None for doc in mock_db["incident_events"].docs)


def test_dry_run_never_calls_provider_or_writes(
    mock_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Dry run selects targets but performs no provider calls or writes."""
    storage = _storage(mock_db)
    storage.insert_events(sample_demo_events)
    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    result = service.run(incident_id="INC-2026-042", dry_run=True)

    assert result.dry_run is True
    assert result.eligible == 17
    assert result.generated == 0
    assert result.updated == 0
    assert provider.calls == []
    assert all(doc["embedding"] is None for doc in mock_db["incident_events"].docs)


def test_backfill_updates_only_embedding_and_preserves_ids_and_metadata(
    mock_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Backfill persists 1536-d vectors while preserving _id and all metadata."""
    storage = _storage(mock_db)
    storage.insert_events(sample_demo_events)
    before = deepcopy(mock_db["incident_events"].docs)
    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider, batch_size=64)

    result = service.run(incident_id="INC-2026-042", mode="missing")
    after = mock_db["incident_events"].docs

    assert result.eligible == 17
    assert result.generated == 17
    assert result.updated == 17
    assert result.failed == 0
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 17

    for old_doc, new_doc in zip(before, after):
        assert old_doc["_id"] == new_doc["_id"]
        assert len(new_doc["embedding"]) == ATLAS_VECTOR_DIMENSIONS
        assert all(isinstance(value, float) for value in new_doc["embedding"])
        old_metadata = {k: v for k, v in old_doc.items() if k != "embedding"}
        new_metadata = {k: v for k, v in new_doc.items() if k != "embedding"}
        assert old_metadata == new_metadata


def test_backfill_is_idempotent_on_second_run(
    mock_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """A completed backfill is skipped on rerun without extra provider calls."""
    storage = _storage(mock_db)
    storage.insert_events(sample_demo_events)
    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    first = service.run(incident_id="INC-2026-042")
    second = service.run(incident_id="INC-2026-042")

    assert first.updated == 17
    assert second.eligible == 0
    assert second.generated == 0
    assert second.updated == 0
    assert len(provider.calls) == 1
    assert service.audit(incident_id="INC-2026-042").valid == 17


def test_dimension_mismatch_fails_before_any_write(
    mock_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """A 768-d provider cannot write into a 1536-d Atlas index."""
    storage = _storage(mock_db)
    storage.insert_events(sample_demo_events)
    provider = FixedDimensionProvider(dimension=768)
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    with pytest.raises(EmbeddingDimensionError, match="dimension 768.*requires 1536"):
        service.run(incident_id="INC-2026-042")

    assert all(doc["embedding"] is None for doc in mock_db["incident_events"].docs)


def test_invalid_mode_repairs_wrong_dimension_vector(mock_db: MockDatabase) -> None:
    """Invalid mode re-embeds existing unusable vectors but missing mode does not."""
    storage = _storage(mock_db)
    storage.insert_events([_single_event()])
    storage.update_event_embedding("INC-2026-042", "ALERT-201", [1.0, 2.0])

    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    assert service.run(incident_id="INC-2026-042", mode="missing").eligible == 0
    result = service.run(incident_id="INC-2026-042", mode="invalid")

    assert result.eligible == 1
    assert result.updated == 1
    doc = mock_db["incident_events"].docs[0]
    assert len(doc["embedding"]) == ATLAS_VECTOR_DIMENSIONS


def test_all_mode_reembeds_valid_vectors(mock_db: MockDatabase) -> None:
    """Explicit all mode can deliberately regenerate already-valid vectors."""
    storage = _storage(mock_db)
    storage.insert_events([_single_event()])
    storage.update_event_embedding(
        "INC-2026-042", "ALERT-201", [0.0] * ATLAS_VECTOR_DIMENSIONS
    )
    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    result = service.run(incident_id="INC-2026-042", mode="all")

    assert result.eligible == 1
    assert result.updated == 1
    assert mock_db["incident_events"].docs[0]["embedding"][0] != 0.0


def test_missing_embedding_text_fails_clearly_without_write(mock_db: MockDatabase) -> None:
    """Events without canonical text fail before provider/write activity."""
    storage = _storage(mock_db)
    event = _single_event()
    event.embedding_text = ""
    storage.insert_events([event])
    provider = FixedDimensionProvider()
    service = EmbeddingBackfillService(storage=storage, provider=provider)

    with pytest.raises(EmbeddingBackfillError, match="missing embedding_text"):
        service.run(incident_id="INC-2026-042")

    assert provider.calls == []
    assert mock_db["incident_events"].docs[0]["embedding"] is None


def test_in_memory_storage_is_refused() -> None:
    """Backfill must not silently run against the in-memory fallback."""
    service = EmbeddingBackfillService(
        storage=StorageService(force_in_memory=True),
        provider=FixedDimensionProvider(),
    )

    with pytest.raises(BackfillConfigurationError, match="live MongoDB connection"):
        service.audit()


def test_classify_embedding_distinguishes_states() -> None:
    """Classification covers absent, null, empty, wrong-dimension, and valid vectors."""
    assert classify_embedding({}, 1536) == "missing"
    assert classify_embedding({"embedding": None}, 1536) == "missing"
    assert classify_embedding({"embedding": []}, 1536) == "missing"
    assert classify_embedding({"embedding": [1.0, 2.0]}, 1536) == "invalid"
    assert classify_embedding({"embedding": ["x"]}, 1536) == "invalid"
    assert classify_embedding({"embedding": [0.1] * 1536}, 1536) == "valid"
