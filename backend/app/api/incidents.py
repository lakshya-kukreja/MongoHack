"""Incident management and deterministic timeline API routes."""

from typing import Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.logging import logger
from app.models.event import (
    EventRecord,
    IncidentSummary,
    IngestRequest,
    IngestResponse,
    TimelineResponse,
    QueryRequest,
    QueryResponse as QueryResponseModel,
)
from app.services.ingestion import parse_incident_data
from app.services.storage import StorageService, get_storage_service
from app.services.timeline import (
    build_timeline_response,
    parse_filter_datetime,
    parse_source_types_filter,
)
from app.services.generator import Generator, get_generator
from app.services.generator import (
    GeneratorTimeoutError,
    GeneratorRateLimitError,
    GeneratorProviderError,
    GeneratorConfigurationError,
    describe_exception_for_logging,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest heterogeneous incident events",
)
async def ingest_events(
    payload: Union[IngestRequest, list[dict[str, Any]]],
    storage: StorageService = Depends(get_storage_service),
) -> IngestResponse:
    """Ingest a batch of raw or normalized incident events.

    Accepts either an IngestRequest object {"incident_id": ..., "events": [...]}
    or a raw list of event dictionaries.
    """
    try:
        if isinstance(payload, IngestRequest):
            incident_id = payload.incident_id
            records = parse_incident_data(
                data_input=payload.events,
                default_incident_id=incident_id,
            )
        else:
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Event payload cannot be empty",
                )
            records = parse_incident_data(data_input=payload)
            incident_id = records[0].incident_id if records else "UNKNOWN"

        count = storage.insert_events(records)
        return IngestResponse(
            incident_id=incident_id,
            ingested_count=count,
            status="success",
        )
    except ValueError as val_err:
        logger.warning(f"Validation failure during ingestion: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(val_err),
        ) from val_err
    except Exception as exc:
        logger.error(f"Unexpected error during ingestion: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest incident records",
        ) from exc


@router.get(
    "",
    response_model=list[IncidentSummary],
    summary="List all available incidents",
)
async def list_incidents(
    storage: StorageService = Depends(get_storage_service),
) -> list[IncidentSummary]:
    """Retrieve high-level summaries of all incidents currently recorded."""
    return storage.list_incidents()


@router.get(
    "/{incident_id}/timeline",
    response_model=TimelineResponse,
    summary="Get deterministic chronological timeline for an incident",
)
async def get_incident_timeline(
    incident_id: str,
    start_time: Optional[str] = Query(
        default=None,
        description="Filter events on or after this ISO-8601 UTC timestamp (inclusive)",
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="Filter events on or before this ISO-8601 UTC timestamp (inclusive)",
    ),
    source_type: Optional[str] = Query(
        default=None,
        description="Comma-delimited source types to include (e.g. 'slack,monitoring_alert')",
    ),
    storage: StorageService = Depends(get_storage_service),
) -> TimelineResponse:
    """Retrieve chronologically ordered events for an incident with optional filtering.

    Timelines are deterministically sorted strictly by verified ISO-8601 timestamps.
    """
    if not storage.incident_exists(incident_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    # Validate ISO-8601 datetime parameters
    try:
        parsed_start = parse_filter_datetime(start_time, "start_time")
        parsed_end = parse_filter_datetime(end_time, "end_time")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid ISO-8601 datetime format for start_time/end_time",
        ) from exc

    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_time cannot be after end_time",
        )

    # Validate source_type filter
    try:
        parse_source_types_filter(source_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    all_events = storage.get_all_incident_events(incident_id)

    return build_timeline_response(
        incident_id=incident_id,
        all_events=all_events,
        start_time=parsed_start,
        end_time=parsed_end,
        source_type=source_type,
    )


@router.get(
    "/{incident_id}/events/{source_id}",
    response_model=EventRecord,
    summary="Get single event detail",
)
async def get_incident_event(
    incident_id: str,
    source_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> EventRecord:
    """Retrieve the full event payload and metadata for an individual source record."""
    if not storage.incident_exists(incident_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    event = storage.get_event(incident_id=incident_id, source_id=source_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{source_id}' not found in incident '{incident_id}'",
        )

    return event


@router.post(
    "/{incident_id}/query",
    response_model=QueryResponseModel,
    summary="Ask an investigation question (RAG)",
)
async def query_incident(
    incident_id: str,
    payload: QueryRequest,
    storage: StorageService = Depends(get_storage_service),
    generator: Generator = Depends(get_generator),
) -> QueryResponseModel:
    """Perform grounded RAG query over incident evidence with citation validation."""
    if not storage.incident_exists(incident_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    
    try:
        result = generator.query(
            incident_id=incident_id,
            query=payload.query,
            limit=payload.limit,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        return QueryResponseModel(
            answer=result.answer,
            citations=result.citations,
            unverified_citations=result.unverified_citations,
            retrieved_events=result.retrieved_events,
        )
    except GeneratorTimeoutError as exc:
        logger.warning(
            "LLM timeout for query on %s: %s",
            incident_id,
            describe_exception_for_logging(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider timed out",
        ) from exc
    except GeneratorRateLimitError as exc:
        logger.warning(
            "LLM rate limit for query on %s: %s",
            incident_id,
            describe_exception_for_logging(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider unavailable or rate-limited",
        ) from exc
    except GeneratorProviderError as exc:
        logger.warning(
            "LLM provider error for query on %s: %s",
            incident_id,
            describe_exception_for_logging(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider unavailable or rate-limited",
        ) from exc
    except GeneratorConfigurationError as exc:
        logger.warning(
            "LLM configuration error for query on %s: %s",
            incident_id,
            describe_exception_for_logging(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider unavailable or rate-limited",
        ) from exc
    except ValueError as exc:
        logger.warning(f"Validation error for query on {incident_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error during query on %s: %s",
            incident_id,
            describe_exception_for_logging(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process query",
        ) from exc
