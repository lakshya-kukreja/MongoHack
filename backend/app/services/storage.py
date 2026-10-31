"""Storage service encapsulating MongoDB Atlas operations and in-memory fallback."""

from datetime import datetime, timezone
from typing import Any, Optional, Union
from pymongo import ReplaceOne
from pymongo.collection import Collection
from pymongo.database import Database
from app.core.config import settings
from app.core.db import check_db_connection, get_database
from app.core.logging import logger
from app.models.event import (
    EventRecord,
    IncidentSummary,
    format_utc_iso,
    parse_to_utc_datetime,
)
from app.services.timeline import filter_timeline_events, sort_events_chronologically


class StorageService:
    """Encapsulates data persistence for incident events."""

    def __init__(
        self,
        database: Optional[Database] = None,
        force_in_memory: bool = False,
    ):
        """Initialize storage service.

        Args:
            database: PyMongo Database instance. If None, resolves from get_database().
            force_in_memory: If True, operates solely in memory (ideal for isolated unit tests).
        """
        self._force_in_memory = force_in_memory
        if force_in_memory:
            self._db = None
        elif database is not None:
            self._db = database
        else:
            self._db = get_database()

        # In-memory store: {(incident_id, source_id): EventRecord}
        self._memory_events: dict[tuple[str, str], EventRecord] = {}

    @property
    def is_in_memory(self) -> bool:
        """True if storage is currently using the in-memory fallback."""
        return self._db is None

    @property
    def collection(self) -> Optional[Collection]:
        """Access the incident_events MongoDB collection if connected."""
        if self._db is not None:
            return self._db["incident_events"]
        return None

    def ping(self) -> bool:
        """Check whether data store is accessible."""
        if self._db is not None:
            try:
                self._db.client.admin.command("ping")
                return True
            except Exception as exc:
                logger.warning(f"MongoDB ping failed: {exc}")
                return False

        if settings.MONGODB_URI and not self._force_in_memory:
            return False

        return True

    def create_indexes(self) -> None:
        """Create necessary MongoDB indexes if connected.

        Indexes created:
        1. Unique compound index on (incident_id, source_id): prevents duplicate events per incident.
        2. Compound timeline index on (incident_id, timestamp): ensures fast chronological range queries.
        3. Standalone index on (timestamp): speeds up cross-incident time window queries.
        4. Standalone index on (source_id): enables rapid lookup across sources.
        5. Facet index on (source_type): accelerates filtering by event category.
        """
        if self.collection is not None:
            try:
                # Unique compound index to enforce uniqueness of source_id per incident
                self.collection.create_index(
                    [("incident_id", 1), ("source_id", 1)],
                    unique=True,
                    name="incident_source_id_unique",
                )
                # Compound index for fast deterministic timeline queries
                self.collection.create_index(
                    [("incident_id", 1), ("timestamp", 1)],
                    name="incident_timestamp_idx",
                )
                # Standalone index on timestamp for time-based operations
                self.collection.create_index(
                    [("timestamp", 1)],
                    name="timestamp_idx",
                )
                # Standalone index on source_id
                self.collection.create_index(
                    [("source_id", 1)],
                    name="source_id_idx",
                )
                # Index on source_type for faceted queries
                self.collection.create_index([("source_type", 1)], name="source_type_idx")
                logger.info("MongoDB indexes verified/created successfully.")
            except Exception as exc:
                logger.warning(f"Could not create MongoDB indexes: {exc}")

    def insert_events(self, events: list[EventRecord]) -> int:
        """Persist a list of validated EventRecords.

        Uses upsert on (incident_id, source_id) to guarantee idempotency and prevent duplicates.

        Args:
            events: List of EventRecord instances.

        Returns:
            Number of events successfully stored.
        """
        if not events:
            return 0

        if self.collection is not None:
            operations: list[ReplaceOne] = []
            for event in events:
                doc = event.model_dump()
                ts = doc.get("timestamp")
                if isinstance(ts, str):
                    doc["timestamp"] = parse_to_utc_datetime(ts)
                elif isinstance(ts, datetime) and ts.tzinfo is None:
                    doc["timestamp"] = ts.replace(tzinfo=timezone.utc)

                ca = doc.get("created_at")
                if isinstance(ca, str):
                    doc["created_at"] = parse_to_utc_datetime(ca)
                elif isinstance(ca, datetime) and ca.tzinfo is None:
                    doc["created_at"] = ca.replace(tzinfo=timezone.utc)
                elif ca is None:
                    doc["created_at"] = datetime.now(timezone.utc)

                # Store source_type as string value
                doc["source_type"] = event.source_type.value

                operations.append(
                    ReplaceOne(
                        {"incident_id": event.incident_id, "source_id": event.source_id},
                        doc,
                        upsert=True,
                    )
                )

            try:
                if hasattr(self.collection, "bulk_write"):
                    self.collection.bulk_write(operations, ordered=False)
                else:
                    for op in operations:
                        self.collection.replace_one(
                            op._filter,
                            op._doc,
                            upsert=True,
                        )
                return len(events)
            except Exception as exc:
                logger.error(f"MongoDB write failed in insert_events: {exc}")
                raise

        # In-memory storage path (idempotent keying on (incident_id, source_id))
        for event in events:
            key = (event.incident_id, event.source_id)
            self._memory_events[key] = event
        return len(events)

    def incident_exists(self, incident_id: str) -> bool:
        """Check if an incident exists in storage."""
        if self.collection is not None:
            try:
                return self.collection.count_documents({"incident_id": incident_id}, limit=1) > 0
            except Exception as exc:
                logger.warning(f"MongoDB query failed in incident_exists: {exc}")

        return any(inc_id == incident_id for inc_id, _ in self._memory_events.keys())

    def count_events(self, incident_id: str) -> int:
        """Count total events for an incident."""
        if self.collection is not None:
            try:
                return self.collection.count_documents({"incident_id": incident_id})
            except Exception as exc:
                logger.warning(f"MongoDB count_documents failed: {exc}")

        return sum(1 for inc_id, _ in self._memory_events.keys() if inc_id == incident_id)

    def get_event(self, incident_id: str, source_id: str) -> Optional[EventRecord]:
        """Fetch a single event by incident_id and source_id."""
        if self.collection is not None:
            try:
                doc = self.collection.find_one(
                    {"incident_id": incident_id, "source_id": source_id},
                    {"_id": 0},
                )
                if doc:
                    return EventRecord.model_validate(doc)
            except Exception as exc:
                logger.warning(f"MongoDB find_one failed: {exc}")

        return self._memory_events.get((incident_id, source_id))

    def get_all_incident_events(self, incident_id: str) -> list[EventRecord]:
        """Fetch all events for an incident, sorted chronologically."""
        if self.collection is not None:
            try:
                cursor = self.collection.find(
                    {"incident_id": incident_id},
                    {"_id": 0},
                ).sort([("timestamp", 1), ("source_id", 1)])
                return [EventRecord.model_validate(doc) for doc in cursor]
            except Exception as exc:
                logger.warning(f"MongoDB get_all_incident_events failed: {exc}")

        events = [ev for (inc_id, _), ev in self._memory_events.items() if inc_id == incident_id]
        return sort_events_chronologically(events)

    def get_timeline_events(
        self,
        incident_id: str,
        start_time: Optional[Union[datetime, str]] = None,
        end_time: Optional[Union[datetime, str]] = None,
        source_types: Optional[Union[list[str], str]] = None,
    ) -> list[EventRecord]:
        """Retrieve filtered events sorted chronologically for an incident."""
        all_events = self.get_all_incident_events(incident_id)
        return filter_timeline_events(
            events=all_events,
            start_time=start_time,
            end_time=end_time,
            source_type=source_types,
        )

    def list_incidents(self) -> list[IncidentSummary]:
        """List summaries of all known incidents."""
        summaries: list[IncidentSummary] = []

        if self.collection is not None:
            try:
                pipeline: list[dict[str, Any]] = [
                    {
                        "$group": {
                            "_id": "$incident_id",
                            "event_count": {"$sum": 1},
                            "start_time": {"$min": "$timestamp"},
                            "end_time": {"$max": "$timestamp"},
                            "services_involved": {"$addToSet": "$channel_or_service"},
                            "events": {
                                "$push": {
                                    "summary": "$summary",
                                    "source_id": "$source_id",
                                }
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
                results = list(self.collection.aggregate(pipeline))
                for item in results:
                    inc_id = item["_id"]
                    start_dt = item.get("start_time")
                    end_dt = item.get("end_time")

                    title = f"Incident {inc_id}"
                    for ev in item.get("events", []):
                        s = ev.get("summary", "")
                        if "declares SEV" in s or "Incident Commander" in s:
                            title = s
                            break

                    services = sorted(list(set(item.get("services_involved", []))))
                    summaries.append(
                        IncidentSummary(
                            incident_id=inc_id,
                            title=title,
                            event_count=item.get("event_count", 0),
                            start_time=format_utc_iso(parse_to_utc_datetime(start_dt))
                            if start_dt
                            else "",
                            end_time=format_utc_iso(parse_to_utc_datetime(end_dt))
                            if end_dt
                            else "",
                            services_involved=services,
                        )
                    )
                return summaries
            except Exception as exc:
                logger.warning(f"MongoDB aggregate failed in list_incidents: {exc}")

        # In-memory grouping
        incident_groups: dict[str, list[EventRecord]] = {}
        for (inc_id, _), ev in self._memory_events.items():
            incident_groups.setdefault(inc_id, []).append(ev)

        for inc_id, ev_list in sorted(incident_groups.items()):
            sorted_list = sort_events_chronologically(ev_list)
            first_ev = sorted_list[0]
            last_ev = sorted_list[-1]

            title = f"Incident {inc_id}"
            for ev in sorted_list:
                if "declares SEV" in ev.summary or "Incident Commander" in ev.summary:
                    title = ev.summary
                    break

            services = sorted(list({ev.channel_or_service for ev in sorted_list}))
            summaries.append(
                IncidentSummary(
                    incident_id=inc_id,
                    title=title,
                    event_count=len(sorted_list),
                    start_time=format_utc_iso(first_ev.timestamp) or "",
                    end_time=format_utc_iso(last_ev.timestamp) or "",
                    services_involved=services,
                )
            )

        return summaries

    def clear_data(self, incident_id: Optional[str] = None) -> None:
        """Clear data in storage (primarily for testing)."""
        if self.collection is not None:
            try:
                if incident_id:
                    self.collection.delete_many({"incident_id": incident_id})
                else:
                    self.collection.delete_many({})
            except Exception as exc:
                logger.warning(f"MongoDB clear_data failed: {exc}")

        if incident_id:
            keys_to_del = [k for k in self._memory_events.keys() if k[0] == incident_id]
            for k in keys_to_del:
                del self._memory_events[k]
        else:
            self._memory_events.clear()


# Default singleton instance
_default_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """FastAPI dependency for accessing the active StorageService."""
    global _default_storage_service
    if _default_storage_service is None:
        _default_storage_service = StorageService()
        _default_storage_service.create_indexes()
    return _default_storage_service


def set_storage_service(service: StorageService) -> None:
    """Override default storage service (useful for testing)."""
    global _default_storage_service
    _default_storage_service = service


def reset_storage_service() -> None:
    """Reset the singleton storage service instance (useful for lifecycle cleanup and testing)."""
    global _default_storage_service
    _default_storage_service = None
