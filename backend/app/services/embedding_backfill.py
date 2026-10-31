"""Safe, idempotent embedding backfill for already-ingested incident events.

The backfill deliberately updates only the ``embedding`` field through a targeted
``$set``. It never replaces documents, ``_id`` values, source identifiers,
timestamps, or raw metadata. Vectors are validated against the Atlas vector
index dimension before any write occurs.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.services.embeddings import (
    EmbeddingProvider,
    generate_embeddings_batch,
    validate_embedding_dimension,
)
from app.services.storage import StorageService

# Must match backend/atlas_vector_index.json (numDimensions).
ATLAS_VECTOR_DIMENSIONS = 1536
DEFAULT_BACKFILL_BATCH_SIZE = 64
BACKFILL_MODES = ("missing", "invalid", "all")

BackfillMode = Literal["missing", "invalid", "all"]


class EmbeddingBackfillError(Exception):
    """Base exception for embedding backfill failures."""


class BackfillConfigurationError(EmbeddingBackfillError):
    """Raised when the backfill target or configuration is unsafe/invalid."""


@dataclass
class EmbeddingAudit:
    """Read-only summary of embedding coverage for the selected events."""

    scanned: int = 0
    missing: int = 0
    invalid: int = 0
    valid: int = 0
    dimensions: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "missing": self.missing,
            "invalid": self.invalid,
            "valid": self.valid,
            "dimensions": dict(self.dimensions),
        }


@dataclass
class BackfillResult:
    """Result of a backfill run, including the pre-run audit."""

    audit: EmbeddingAudit
    mode: str
    expected_dimension: int
    eligible: int = 0
    generated: int = 0
    updated: int = 0
    failed: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit": self.audit.to_dict(),
            "mode": self.mode,
            "expected_dimension": self.expected_dimension,
            "eligible": self.eligible,
            "generated": self.generated,
            "updated": self.updated,
            "failed": self.failed,
            "dry_run": self.dry_run,
        }


def _is_numeric_vector(value: Any) -> bool:
    """Return True for a non-empty finite numeric list/tuple."""
    if not isinstance(value, (list, tuple)) or not value:
        return False
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
        if not math.isfinite(float(item)):
            return False
    return True


def classify_embedding(doc: dict[str, Any], expected_dimension: int) -> str:
    """Classify a document's embedding as ``missing``, ``invalid``, or ``valid``."""
    if "embedding" not in doc:
        return "missing"
    embedding = doc.get("embedding")
    if embedding is None or embedding == []:
        return "missing"
    if _is_numeric_vector(embedding) and len(embedding) == expected_dimension:
        return "valid"
    return "invalid"


def _is_eligible(status: str, mode: BackfillMode) -> bool:
    if mode == "missing":
        return status == "missing"
    if mode == "invalid":
        return status in {"missing", "invalid"}
    if mode == "all":
        return True
    raise BackfillConfigurationError(
        f"Unsupported backfill mode '{mode}'; expected one of {BACKFILL_MODES}"
    )


class EmbeddingBackfillService:
    """Backfill embeddings for existing events without replacing metadata."""

    def __init__(
        self,
        storage: StorageService,
        provider: Optional[EmbeddingProvider] = None,
        expected_dimension: int = ATLAS_VECTOR_DIMENSIONS,
        batch_size: int = DEFAULT_BACKFILL_BATCH_SIZE,
    ):
        """Initialize the backfill service.

        Args:
            storage: Connected StorageService for the target MongoDB collection.
            provider: Optional injected embedding provider (required for offline tests).
            expected_dimension: Required Atlas vector dimension (1536 by default).
            batch_size: Number of events embedded per provider request.
        """
        if (
            not isinstance(expected_dimension, int)
            or isinstance(expected_dimension, bool)
            or expected_dimension < 1
        ):
            raise BackfillConfigurationError("expected_dimension must be a positive integer")
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise BackfillConfigurationError("batch_size must be a positive integer")

        self.storage = storage
        self.provider = provider
        self.expected_dimension = expected_dimension
        self.batch_size = batch_size

    def _documents(self, incident_id: Optional[str]) -> list[dict[str, Any]]:
        if self.storage.is_in_memory:
            raise BackfillConfigurationError(
                "Embedding backfill requires a live MongoDB connection; "
                "refusing to write to the in-memory fallback store"
            )
        return self.storage.get_event_documents(incident_id=incident_id)

    def audit(self, incident_id: Optional[str] = None) -> EmbeddingAudit:
        """Report embedding coverage without generating vectors or writing data."""
        documents = self._documents(incident_id)
        audit = EmbeddingAudit(scanned=len(documents))
        dimensions: Counter[str] = Counter()

        for doc in documents:
            status = classify_embedding(doc, self.expected_dimension)
            setattr(audit, status, getattr(audit, status) + 1)
            embedding = doc.get("embedding")
            if status == "valid":
                dimensions[str(len(embedding))] += 1
            elif status == "invalid":
                if isinstance(embedding, (list, tuple)):
                    dimensions[f"invalid_len_{len(embedding)}"] += 1
                else:
                    dimensions[f"invalid_{type(embedding).__name__}"] += 1

        audit.dimensions = dict(dimensions)
        return audit

    def run(
        self,
        incident_id: Optional[str] = None,
        mode: BackfillMode = "missing",
        dry_run: bool = False,
    ) -> BackfillResult:
        """Backfill eligible embeddings, validating every vector before writing.

        Args:
            incident_id: Optional incident filter; omit to scan the whole collection.
            mode: ``missing`` (default), ``invalid`` (missing + unusable), or ``all``.
            dry_run: When True, audit and select targets but never call the provider
                or write to MongoDB.

        Returns:
            BackfillResult with audit and write counts.

        Raises:
            BackfillConfigurationError: If the target/configuration is unsafe.
            EmbeddingDimensionError: If any provider vector violates the Atlas index.
            EmbeddingBackfillError: If an eligible event lacks canonical embedding text.
        """
        if mode not in BACKFILL_MODES:
            raise BackfillConfigurationError(
                f"Unsupported backfill mode '{mode}'; expected one of {BACKFILL_MODES}"
            )

        documents = self._documents(incident_id)
        audit = self.audit(incident_id)
        selected = [
            doc
            for doc in documents
            if _is_eligible(classify_embedding(doc, self.expected_dimension), mode)
        ]

        result = BackfillResult(
            audit=audit,
            mode=mode,
            expected_dimension=self.expected_dimension,
            eligible=len(selected),
            dry_run=dry_run,
        )
        if not selected or dry_run:
            return result

        texts: list[str] = []
        for doc in selected:
            text = str(doc.get("embedding_text") or "").strip()
            if not text:
                raise EmbeddingBackfillError(
                    f"Event '{doc.get('source_id')}' is missing embedding_text; "
                    "cannot generate an embedding"
                )
            texts.append(text)

        # Generate and validate every vector before writing anything. This keeps
        # provider failures or dimension mismatches from causing partial writes.
        vectors = generate_embeddings_batch(
            texts,
            batch_size=self.batch_size,
            provider=self.provider,
        )
        if len(vectors) != len(selected):
            raise EmbeddingBackfillError(
                f"Provider returned {len(vectors)} vectors for {len(selected)} events"
            )
        for doc, vector in zip(selected, vectors):
            validate_embedding_dimension(
                vector,
                self.expected_dimension,
                context=f"embedding for event '{doc.get('source_id')}'",
            )
        result.generated = len(vectors)

        for doc, vector in zip(selected, vectors):
            updated = self.storage.update_event_embedding(
                incident_id=str(doc.get("incident_id")),
                source_id=str(doc.get("source_id")),
                embedding=list(vector),
            )
            if updated:
                result.updated += 1
            else:
                result.failed += 1

        return result
