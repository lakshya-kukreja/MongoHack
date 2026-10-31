"""MongoDB Atlas Vector Search retrieval service.

Orchestrates $vectorSearch with metadata pre-filtering by incident_id and
optional time window constraints. Returns ranked candidate events with
relevance scores.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

from app.core.config import settings
from app.core.logging import logger
from app.models.event import EventRecord, parse_to_utc_datetime
from app.services.embeddings import EmbeddingError, get_embedding_provider


class RetrievalError(Exception):
    """Base exception for retrieval failures."""


class RetrievalConfigurationError(RetrievalError):
    """Raised when retrieval configuration is invalid."""


class VectorIndexNotFoundError(RetrievalError):
    """Raised when the Atlas vector index is missing."""


class RetrievalService:
    """Service for semantic retrieval using MongoDB Atlas Vector Search."""

    DEFAULT_INDEX_NAME = "vector_index"
    DEFAULT_NUM_CANDIDATES = 50
    DEFAULT_LIMIT = 10

    def __init__(
        self,
        database: Any = None,
        index_name: Optional[str] = None,
        embedding_provider: Any = None,
        num_candidates: int = DEFAULT_NUM_CANDIDATES,
    ):
        self._db = database
        # The index name is deployment-specific: Atlas silently returns zero
        # results (instead of raising) when ``$vectorSearch`` targets an index
        # that does not exist, so mismatches must be configurable and visible.
        configured_index = (index_name or settings.VECTOR_INDEX_NAME or "").strip()
        self.index_name = configured_index or self.DEFAULT_INDEX_NAME
        self._embedding_provider = embedding_provider
        self.num_candidates = num_candidates

    @property
    def collection(self):
        if self._db is not None:
            return self._db["incident_events"]
        return None

    def _assert_configured_index_available(self) -> None:
        """Raise if the configured index is missing or not queryable.

        Atlas ``$vectorSearch`` returns an empty result set rather than an
        error when the index name is unknown, which previously surfaced as a
        misleading insufficient-evidence answer. This check only runs after an
        empty result set so healthy queries pay no extra cost.
        """
        collection = self.collection
        if collection is None or not hasattr(collection, "list_search_indexes"):
            return

        try:
            indexes = list(collection.list_search_indexes())
        except Exception as exc:  # pragma: no cover - depends on Atlas privileges
            logger.debug(f"Could not list Atlas search indexes: {exc}")
            return

        named = [idx for idx in indexes if isinstance(idx, dict) and idx.get("name")]
        if not named:
            # No metadata available (e.g. a mock); do not mask legitimate empties.
            return

        match = next((idx for idx in named if idx["name"] == self.index_name), None)
        if match is None:
            available = ", ".join(sorted(str(idx["name"]) for idx in named))
            raise VectorIndexNotFoundError(
                f"Atlas vector search index '{self.index_name}' not found "
                f"(available: {available})"
            )

        status = match.get("status")
        queryable = match.get("queryable")
        if (isinstance(status, str) and status.upper() != "READY") or queryable is False:
            raise VectorIndexNotFoundError(
                f"Atlas vector search index '{self.index_name}' is not ready "
                f"(status={status!r}, queryable={queryable!r})"
            )

    def _get_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for the query using the configured embedding provider."""
        try:
            provider = self._embedding_provider or get_embedding_provider()
            return provider.embed_texts([query])[0]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise RetrievalError(f"Failed to generate query embedding: {exc}") from exc

    def search(
        self,
        incident_id: str,
        query: str,
        limit: int = DEFAULT_LIMIT,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        source_types: Optional[Union[list[str], str]] = None,
        num_candidates: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Perform vector search with incident_id pre-filtering.
        
        Returns list of dicts with event fields and search score.
        """
        if not incident_id or not incident_id.strip():
            raise RetrievalConfigurationError("incident_id is required")
        if not query or not query.strip():
            raise RetrievalConfigurationError("query is required")
        if limit < 1:
            raise RetrievalConfigurationError("limit must be positive")
        
        query_embedding = self._get_query_embedding(query)
        collection = self.collection
        if collection is None:
            raise RetrievalError("No database connection available for vector search")
        
        # Build filter
        filter_conditions: dict[str, Any] = {"incident_id": {"$eq": incident_id}}
        
        # Time range filtering if specified
        time_filter: dict[str, Any] = {}
        if start_time is not None:
            if isinstance(start_time, str):
                start_time = parse_to_utc_datetime(start_time)
            time_filter["$gte"] = start_time
        if end_time is not None:
            if isinstance(end_time, str):
                end_time = parse_to_utc_datetime(end_time)
            time_filter["$lte"] = end_time
        if time_filter:
            filter_conditions["timestamp"] = time_filter
        
        # Source type filtering
        if source_types is not None:
            if isinstance(source_types, str):
                source_types = [s.strip() for s in source_types.split(",") if s.strip()]
            if source_types:
                filter_conditions["source_type"] = {"$in": source_types}
        
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self.index_name,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": num_candidates or self.num_candidates,
                    "limit": limit,
                    "filter": filter_conditions,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "source_id": 1,
                    "incident_id": 1,
                    "timestamp": 1,
                    "source_type": 1,
                    "author_or_actor": 1,
                    "channel_or_service": 1,
                    "summary": 1,
                    "raw_content": 1,
                    "structured_payload": 1,
                    "tags": 1,
                    "embedding_text": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        
        try:
            results = list(collection.aggregate(pipeline))
        except Exception as exc:
            # Check for common Atlas vector search errors
            error_msg = str(exc).lower()
            if "index" in error_msg and ("not found" in error_msg or "does not exist" in error_msg):
                raise VectorIndexNotFoundError(
                    f"Atlas vector search index '{self.index_name}' not found or not ready"
                ) from exc
            if "dimension" in error_msg:
                raise RetrievalError(f"Embedding dimension mismatch: {exc}") from exc
            raise RetrievalError(f"Vector search failed: {exc}") from exc

        if not results:
            # Atlas returns [] (not an error) when the index name is wrong.
            # Surface that misconfiguration instead of a false "no evidence".
            self._assert_configured_index_available()

        return results

    def search_events(
        self,
        incident_id: str,
        query: str,
        limit: int = DEFAULT_LIMIT,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        source_types: Optional[Union[list[str], str]] = None,
    ) -> list[EventRecord]:
        """Perform vector search and return EventRecord objects."""
        results = self.search(
            incident_id=incident_id,
            query=query,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            source_types=source_types,
        )
        events = []
        for doc in results:
            try:
                # Remove score before validation if present
                doc_copy = dict(doc)
                doc_copy.pop("score", None)
                events.append(EventRecord.model_validate(doc_copy))
            except Exception as exc:
                logger.warning(f"Failed to validate retrieved event: {exc}")
                continue
        return events

    def search_with_scores(
        self,
        incident_id: str,
        query: str,
        limit: int = DEFAULT_LIMIT,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        source_types: Optional[Union[list[str], str]] = None,
    ) -> list[tuple[EventRecord, float]]:
        """Perform vector search and return (EventRecord, score) tuples."""
        results = self.search(
            incident_id=incident_id,
            query=query,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            source_types=source_types,
        )
        events_with_scores = []
        for doc in results:
            try:
                doc_copy = dict(doc)
                score = doc_copy.pop("score", 0.0)
                event = EventRecord.model_validate(doc_copy)
                events_with_scores.append((event, float(score)))
            except Exception as exc:
                logger.warning(f"Failed to validate retrieved event: {exc}")
                continue
        return events_with_scores


_default_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service(database: Any = None) -> RetrievalService:
    """Get or create default retrieval service instance."""
    global _default_retrieval_service
    if _default_retrieval_service is None or database is not None:
        from app.core.db import get_database

        db = database if database is not None else get_database()
        _default_retrieval_service = RetrievalService(database=db)
    return _default_retrieval_service


# Module-contract aliases
retrieve = RetrievalService.search
vector_search = RetrievalService.search
