"""MongoDB Atlas Vector Search retrieval service.

Orchestrates $vectorSearch with metadata pre-filtering by incident_id and
optional time window constraints. Returns ranked candidate events with
relevance scores. Falls back to in-memory ranking when Atlas is not connected.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional, Union

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
        index_name: str = DEFAULT_INDEX_NAME,
        embedding_provider: Any = None,
        num_candidates: int = DEFAULT_NUM_CANDIDATES,
    ):
        self._db = database
        self.index_name = index_name
        self._embedding_provider = embedding_provider
        self.num_candidates = num_candidates

    @property
    def collection(self):
        if self._db is not None:
            return self._db["incident_events"]
        return None

    def _get_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for the query using the configured embedding provider."""
        try:
            provider = self._embedding_provider or get_embedding_provider()
            return provider.embed_texts([query])[0]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise RetrievalError(f"Failed to generate query embedding: {exc}") from exc

    def _search_in_memory(
        self,
        incident_id: str,
        query: str,
        limit: int = DEFAULT_LIMIT,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        source_types: Optional[Union[list[str], str]] = None,
    ) -> list[dict[str, Any]]:
        """In-memory retrieval fallback when MongoDB Atlas Vector Search is not connected."""
        from app.services.storage import get_storage_service

        storage = get_storage_service()
        candidate_events = storage.get_timeline_events(
            incident_id=incident_id,
            start_time=start_time,
            end_time=end_time,
            source_types=source_types,
        )
        if not candidate_events:
            return []

        # Extract meaningful terms
        terms = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_\-\.]+\b", query)]
        stopwords = {
            "what", "who", "which", "when", "where", "why", "how", "is", "was",
            "are", "were", "the", "a", "an", "and", "or", "in", "on", "at", "to",
            "for", "of", "with", "by", "this", "that", "it", "did", "does", "do",
            "have", "has", "had", "outage", "incident", "issue", "problem", "tell", "me",
        }
        query_terms = [t for t in terms if t not in stopwords and len(t) > 1]
        if not query_terms:
            query_terms = terms

        # Scoring heuristics
        scored: list[tuple[EventRecord, float]] = []
        for ev in candidate_events:
            score = 0.0
            summary_lower = (ev.summary or "").lower()
            content_lower = (ev.raw_content or "").lower()
            actor_lower = (ev.author_or_actor or "").lower()
            service_lower = (ev.channel_or_service or "").lower()
            tags_lower = " ".join((t or "").lower() for t in (ev.tags or []))
            sid_lower = ev.source_id.lower()

            for term in query_terms:
                if term == sid_lower:
                    score += 15.0
                if term in summary_lower:
                    score += 4.0
                if term in tags_lower:
                    score += 3.0
                if term in actor_lower or term in service_lower:
                    score += 3.0
                if term in content_lower:
                    score += 1.0

            normalized_score = 0.50 + min(0.48, score * 0.04) if score > 0 else 0.40
            scored.append((ev, normalized_score))

        # Sort by score descending, then chronological ascending
        scored.sort(key=lambda item: (-item[1], item[0].timestamp))

        results: list[dict[str, Any]] = []
        for ev, score in scored[:limit]:
            doc = {
                "source_id": ev.source_id,
                "incident_id": ev.incident_id,
                "timestamp": ev.timestamp,
                "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
                "author_or_actor": ev.author_or_actor,
                "channel_or_service": ev.channel_or_service,
                "summary": ev.summary,
                "raw_content": ev.raw_content,
                "structured_payload": ev.structured_payload,
                "tags": ev.tags,
                "embedding_text": ev.embedding_text,
                "score": score,
            }
            results.append(doc)
        return results

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
        """Perform vector search with incident_id pre-filtering, or in-memory fallback."""
        if not incident_id or not incident_id.strip():
            raise RetrievalConfigurationError("incident_id is required")
        if not query or not query.strip():
            raise RetrievalConfigurationError("query is required")
        if limit < 1:
            raise RetrievalConfigurationError("limit must be positive")

        collection = self.collection
        if collection is None:
            return self._search_in_memory(
                incident_id=incident_id,
                query=query,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                source_types=source_types,
            )

        # Build filter for MongoDB
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

        try:
            query_embedding = self._get_query_embedding(query)
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
            results = list(collection.aggregate(pipeline))
            if results:
                return results
            # If vector search returned 0 results, fall back to in-memory keyword matching
            return self._search_in_memory(
                incident_id=incident_id,
                query=query,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                source_types=source_types,
            )
        except Exception as exc:
            logger.warning(f"Vector search failed ({exc}), falling back to in-memory search")
            return self._search_in_memory(
                incident_id=incident_id,
                query=query,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                source_types=source_types,
            )

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
